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
enum class BoundaryAxis { TH16, QV16 };
enum class BoundaryKind { SW_PERCENT_048, OBSERVED_FRACTION_EQ_ONE };
std::uint64_t raw_bits(double v) {
    std::uint64_t out = 0;
    std::memcpy(&out, &v, sizeof(out));
    return out;
}
double double_from_bits(std::uint64_t v) {
    double out = 0.0;
    std::memcpy(&out, &v, sizeof(out));
    return out;
}
std::string word_fixed(double v) {
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << raw_bits(v);
    return out.str();
}
std::uint64_t ordered_bits(double v) {
    constexpr std::uint64_t SIGN = std::uint64_t{1} << 63;
    const auto raw = raw_bits(v);
    return (raw & SIGN) ? ~raw : (raw | SIGN);
}
std::uint64_t ulp_distance(double a, double b) {
    const auto x = ordered_bits(a), y = ordered_bits(b);
    return x >= y ? x - y : y - x;
}
struct ActivationObservation {
    double coordinate = 0.0, th16 = 0.0, qv16 = 0.0, physical_t16 = 0.0;
    double qv_input = 0.0, qs1 = 0.0, qs1_safe = 0.0, nc_input = 0.0, nccn_input = 0.0, dtcld = 0.0;
    double sw_percent = 0.0, activated_fraction = 0.0;
    double ncact_raw = 0.0, ncact = 0.0;
    double ncact_rate_cap = 0.0, ncact_raw_minus_cap = 0.0;
    double sw_ratio = 0.0, safe_pow_clamped_base_diagnostic = 0.0;
    double activation_fraction_one = 0.0, activation_fraction_pow = 0.0;
    double activation_fraction_min_output = 0.0;
    double ncact_preclamp_fma = 0.0, ncact_clamped_numerator = 0.0;
    double ncact_nccn_rate_cap = 0.0, ncact_min_output = 0.0;
    double nc_after_activation = 0.0, nccn_after_activation = 0.0;
    double nccn_final = 0.0, final_nc16 = 0.0, final_nccn16 = 0.0;
    double d1_t = 0.0, d1_t1 = 0.0, d1_work2 = 0.0, d1_pgmlt_raw = 0.0;
    bool nccn_floor_active = false, nccn_cap_active = false;
    bool d1_warm = false, d1_snow_active = false, d1_graupel_active = false;
    bool d1_psmlt_raw_candidate = false, d1_pgmlt_raw_candidate = false;
    bool predicate = false, sw_positive = false;
    bool ncact_cap_active = false, ncact_cap_tie = false;
    bool activation_fraction_pow_lt_one = false, activation_fraction_pow_eq_one = false;
    bool activation_fraction_pow_gt_one = false;
    bool ncact_raw_lt_nccn_rate_cap = false, ncact_raw_eq_nccn_rate_cap = false;
    bool ncact_raw_gt_nccn_rate_cap = false;
    std::uint64_t coordinate_bits = 0;
    std::string event_id;
    std::int64_t forward_call_ordinal = 0;
    std::int64_t trace_index = -1;
};
ActivationObservation observe_activation(const Eval& e, const Input& in,
                                         BoundaryAxis axis, double coordinate,
                                         BoundaryKind kind) {
    ActivationObservation r;
    r.coordinate = coordinate;
    r.th16 = axis == BoundaryAxis::TH16 ? coordinate : in.state[TH16];
    r.qv16 = axis == BoundaryAxis::QV16 ? coordinate : in.state[QV16];
    r.physical_t16 = r.th16 * in.forcing[PII16];
    r.coordinate_bits = raw_bits(coordinate);
    const auto& s = e.stages;
    r.qv_input = stage_value(s, "fd_satadj_inner.qv_input");
    r.qs1 = stage_value(s, "fd_satadj_inner.qs1");
    r.qs1_safe = std::max(r.qs1, 1.0e-9);
    r.nc_input = stage_value(s, "fd_satadj_inner.nc_input");
    r.nccn_input = stage_value(s, "fd_satadj_inner.nccn_input");
    r.dtcld = in.dt;
    r.sw_percent = stage_value(s, "fd_satadj_inner.sw_percent");
    r.sw_ratio = stage_value(s, "fd_satadj_inner.sw_ratio");
    r.sw_positive = stage_value(s, "fd_satadj_inner.sw_positive") != 0.0;
    r.activated_fraction = stage_value(s, "fd_satadj_inner.activated_fraction");
    r.safe_pow_clamped_base_diagnostic = stage_value(s, "fd_satadj_inner.safe_pow_clamped_base_diagnostic");
    r.activation_fraction_one = stage_value(s, "fd_satadj_inner.activation_fraction_one");
    r.activation_fraction_pow = stage_value(s, "fd_satadj_inner.activation_fraction_pow");
    r.activation_fraction_min_output = stage_value(s, "fd_satadj_inner.activation_fraction_min_output");
    r.activation_fraction_pow_lt_one = stage_value(s, "fd_satadj_inner.activation_fraction_pow_lt_one") != 0.0;
    r.activation_fraction_pow_eq_one = stage_value(s, "fd_satadj_inner.activation_fraction_pow_eq_one") != 0.0;
    r.activation_fraction_pow_gt_one = stage_value(s, "fd_satadj_inner.activation_fraction_pow_gt_one") != 0.0;
    r.ncact_raw = stage_value(s, "fd_satadj_inner.ncact_raw");
    r.ncact = stage_value(s, "fd_satadj_inner.ncact");
    r.ncact_preclamp_fma = stage_value(s, "fd_satadj_inner.ncact_preclamp_fma");
    r.ncact_clamped_numerator = stage_value(s, "fd_satadj_inner.ncact_clamped_numerator");
    r.ncact_nccn_rate_cap = stage_value(s, "fd_satadj_inner.ncact_nccn_rate_cap");
    r.ncact_min_output = stage_value(s, "fd_satadj_inner.ncact_min_output");
    r.ncact_rate_cap = std::max(r.nccn_input, 0.0) / r.dtcld;
    r.ncact_raw_minus_cap = r.ncact_raw - r.ncact_rate_cap;
    r.ncact_cap_active = r.ncact_raw > r.ncact_rate_cap;
    r.ncact_cap_tie = r.ncact_raw == r.ncact_rate_cap;
    r.ncact_raw_lt_nccn_rate_cap = stage_value(s, "fd_satadj_inner.ncact_raw_lt_nccn_rate_cap") != 0.0;
    r.ncact_raw_eq_nccn_rate_cap = stage_value(s, "fd_satadj_inner.ncact_raw_eq_nccn_rate_cap") != 0.0;
    r.ncact_raw_gt_nccn_rate_cap = stage_value(s, "fd_satadj_inner.ncact_raw_gt_nccn_rate_cap") != 0.0;
    r.nc_after_activation = stage_value(s, "fd_satadj_inner.nc_after_activation");
    r.nccn_after_activation = stage_value(s, "fd_satadj_inner.nccn_after_activation");
    r.nccn_final = stage_value(s, "fd_satadj_inner.nccn_final");
    r.nccn_floor_active = stage_value(s, "fd_satadj_inner.nccn_floor_active") != 0.0;
    r.nccn_cap_active = stage_value(s, "fd_satadj_inner.nccn_cap_active") != 0.0;
    r.d1_t = stage_value(s, "d1_melt_producer.t");
    r.d1_t1 = stage_value(s, "d1_melt_producer.t1");
    r.d1_work2 = stage_value(s, "d1_melt_producer.work2");
    r.d1_pgmlt_raw = stage_value(s, "d1_melt_producer.pgmlt_raw");
    r.d1_warm = stage_value(s, "d1_melt_producer.warm") != 0.0;
    r.d1_snow_active = stage_value(s, "d1_melt_producer.snow_active") != 0.0;
    r.d1_graupel_active = stage_value(s, "d1_melt_producer.graupel_active") != 0.0;
    r.d1_psmlt_raw_candidate = stage_value(s, "d1_melt_producer.psmlt_dt") ==
                               stage_value(s, "d1_melt_producer.psmlt_capped");
    r.d1_pgmlt_raw_candidate = stage_value(s, "d1_melt_producer.pgmlt_dt") ==
                               stage_value(s, "d1_melt_producer.pgmlt_capped");
    r.predicate = kind == BoundaryKind::SW_PERCENT_048
        ? r.sw_percent >= 0.48 : r.activated_fraction >= 1.0;
    const auto final = values(e.final);
    r.final_nc16 = final[8 * K + 15];
    r.final_nccn16 = final[7 * K + 15];
    return r;
}
Eval activation_value_call(const Input& in, const Map& map, BoundaryAxis axis, double coordinate) {
    auto state = in.state;
    if (axis == BoundaryAxis::TH16) state[TH16] = coordinate;
    else state[QV16] = coordinate;
    torch::NoGradGuard guard;
    return map(torch::from_blob(state.data(), {STATE,K}, F64).clone(), true);
}
struct BoundarySearch {
    BoundaryAxis axis;
    BoundaryKind kind;
    ActivationObservation lower, upper;
    std::vector<ActivationObservation> trace;
    std::size_t calls = 0;
};
BoundarySearch bisect_activation_boundary(const Input& in, const Map& map,
                                          BoundaryAxis axis, BoundaryKind kind,
                                          double lower_input, double upper_input,
                                          std::int64_t& forward_call_counter) {
    BoundarySearch out{axis, kind, {}, {}, {}, 0};
    auto evaluate = [&](double coordinate) {
        auto e = activation_value_call(in, map, axis, coordinate);
        ++out.calls;
        ++forward_call_counter;
        auto row = observe_activation(e, in, axis, coordinate, kind);
        row.trace_index = static_cast<std::int64_t>(out.calls - 1);
        row.forward_call_ordinal = forward_call_counter;
        const std::string axis_name = axis == BoundaryAxis::TH16 ? "th16" : "qv16";
        const std::string kind_name = kind == BoundaryKind::SW_PERCENT_048
            ? "sw_percent_0p48" : "activated_fraction_ge_1_observed_value";
        row.event_id = "bisection/" + axis_name + "/" + kind_name + "/trace_" +
                       std::to_string(row.trace_index);
        return row;
    };
    out.lower = evaluate(lower_input);
    out.upper = evaluate(upper_input);
    need(out.lower.coordinate < out.upper.coordinate, "activation bracket order");
    need(out.lower.predicate != out.upper.predicate, "activation threshold not bracketed");
    out.trace.push_back(out.lower);
    out.trace.push_back(out.upper);
    auto low_bits = raw_bits(out.lower.coordinate);
    auto high_bits = raw_bits(out.upper.coordinate);
    need(low_bits < high_bits, "activation positive f64 ordered-word bracket");
    while (high_bits - low_bits > 1) {
        const auto mid_bits = low_bits + (high_bits - low_bits) / 2;
        const double mid = double_from_bits(mid_bits);
        auto row = evaluate(mid);
        out.trace.push_back(row);
        if (row.predicate == out.lower.predicate) {
            out.lower = row;
            low_bits = mid_bits;
        } else {
            out.upper = row;
            high_bits = mid_bits;
        }
    }
    return out;
}
void emit_activation_observation(std::ostream& out, const ActivationObservation& r) {
    out << "{\"event_id\":\"" << r.event_id << "\",\"forward_call_ordinal\":" << r.forward_call_ordinal
        << ",\"trace_index\":" << r.trace_index
        << ",\"input\":" << std::setprecision(17) << r.coordinate
        << ",\"input_word\":\"" << word_fixed(r.coordinate) << "\",\"predicate\":"
        << (r.predicate ? "true" : "false")
        << ",\"th16\":" << r.th16 << ",\"qv16\":" << r.qv16
        << ",\"physical_t16\":" << r.physical_t16
        << ",\"dtcld\":" << r.dtcld
        << ",\"qv_input\":" << r.qv_input << ",\"qv_input_word\":\"" << word_fixed(r.qv_input)
        << "\",\"qs1\":" << r.qs1 << ",\"qs1_safe\":" << r.qs1_safe
        << ",\"nc_input\":" << r.nc_input << ",\"nccn_input\":" << r.nccn_input
        << ",\"sw_percent\":" << r.sw_percent << ",\"sw_percent_word\":\"" << word_fixed(r.sw_percent)
        << "\",\"sw_positive\":" << (r.sw_positive ? "true" : "false")
        << ",\"activated_fraction\":" << r.activated_fraction
        << ",\"activated_fraction_word\":\"" << word_fixed(r.activated_fraction)
        << "\",\"ncact_raw\":" << r.ncact_raw << ",\"ncact\":" << r.ncact
        << ",\"ncact_rate_cap\":" << r.ncact_rate_cap
        << ",\"ncact_raw_minus_cap\":" << r.ncact_raw_minus_cap
        << ",\"ncact_cap_active\":" << (r.ncact_cap_active ? "true" : "false")
        << ",\"ncact_cap_tie\":" << (r.ncact_cap_tie ? "true" : "false")
        << ",\"nc_after_activation\":" << r.nc_after_activation
        << ",\"nccn_after_activation\":" << r.nccn_after_activation
        << ",\"nccn_final\":" << r.nccn_final
        << ",\"final_nc16\":" << r.final_nc16 << ",\"final_nccn16\":" << r.final_nccn16
        << ",\"nccn_floor_active\":" << (r.nccn_floor_active ? "true" : "false")
        << ",\"nccn_cap_active\":" << (r.nccn_cap_active ? "true" : "false")
        << ",\"operand_values\":{\"sw_ratio\":" << r.sw_ratio
        << ",\"sw_ratio_word\":\"" << word_fixed(r.sw_ratio)
        << "\",\"safe_pow_clamped_base_diagnostic\":" << r.safe_pow_clamped_base_diagnostic
        << ",\"safe_pow_clamped_base_diagnostic_word\":\"" << word_fixed(r.safe_pow_clamped_base_diagnostic)
        << "\",\"activation_fraction_one\":" << r.activation_fraction_one
        << ",\"activation_fraction_pow\":" << r.activation_fraction_pow
        << ",\"activation_fraction_pow_word\":\"" << word_fixed(r.activation_fraction_pow)
        << "\",\"activation_fraction_min_output\":" << r.activation_fraction_min_output
        << ",\"activation_fraction_pow_lt_one\":" << (r.activation_fraction_pow_lt_one ? "true" : "false")
        << ",\"activation_fraction_pow_eq_one\":" << (r.activation_fraction_pow_eq_one ? "true" : "false")
        << ",\"activation_fraction_pow_gt_one\":" << (r.activation_fraction_pow_gt_one ? "true" : "false")
        << ",\"ncact_preclamp_fma\":" << r.ncact_preclamp_fma
        << ",\"ncact_clamped_numerator\":" << r.ncact_clamped_numerator
        << ",\"ncact_nccn_rate_cap\":" << r.ncact_nccn_rate_cap
        << ",\"ncact_nccn_rate_cap_word\":\"" << word_fixed(r.ncact_nccn_rate_cap)
        << "\",\"ncact_min_output\":" << r.ncact_min_output
        << ",\"ncact_raw_lt_nccn_rate_cap\":" << (r.ncact_raw_lt_nccn_rate_cap ? "true" : "false")
        << ",\"ncact_raw_eq_nccn_rate_cap\":" << (r.ncact_raw_eq_nccn_rate_cap ? "true" : "false")
        << ",\"ncact_raw_gt_nccn_rate_cap\":" << (r.ncact_raw_gt_nccn_rate_cap ? "true" : "false") << "}"
        << ",\"d1_branch\":{\"warm\":" << (r.d1_warm ? "true" : "false")
        << ",\"snow_active\":" << (r.d1_snow_active ? "true" : "false")
        << ",\"graupel_active\":" << (r.d1_graupel_active ? "true" : "false")
        << ",\"psmlt_raw_candidate\":" << (r.d1_psmlt_raw_candidate ? "true" : "false")
        << ",\"pgmlt_raw_candidate\":" << (r.d1_pgmlt_raw_candidate ? "true" : "false")
        << ",\"t\":" << r.d1_t << ",\"t1\":" << r.d1_t1
        << ",\"work2\":" << r.d1_work2 << ",\"pgmlt_raw\":" << r.d1_pgmlt_raw << "}}";
}
void emit_activation_gap(std::ostream& out, const char* name, double lower, double upper) {
    const auto distance = ulp_distance(lower, upper);
    out << '"' << name << "\":{\"lower\":" << std::setprecision(17) << lower
        << ",\"upper\":" << upper << ",\"delta\":" << upper - lower
        << ",\"ulp_distance\":" << distance
        << ",\"resolution_status\":\""
        << (distance <= 1 ? "unresolved_at_f64_output_resolution" : "resolved_above_one_output_ulp")
        << "\"}";
}
void emit_boundary_search(std::ostream& out, const BoundarySearch& search) {
    const auto lower_bits = raw_bits(search.lower.coordinate);
    const auto upper_bits = raw_bits(search.upper.coordinate);
    out << "{\"axis\":\"" << (search.axis == BoundaryAxis::TH16 ? "th16" : "qv16")
        << "\",\"predicate\":\""
        << (search.kind == BoundaryKind::SW_PERCENT_048 ? "sw_percent_gte_0p48" : "activated_fraction_ge_1_observed_value")
        << "\",\"lower\":";
    emit_activation_observation(out, search.lower);
    out << ",\"upper\":";
    emit_activation_observation(out, search.upper);
    out << ",\"adjacent_f64_words\":" << (upper_bits - lower_bits == 1 ? "true" : "false")
        << ",\"input_word_gap\":" << (upper_bits - lower_bits)
        << ",\"value_only_calls\":" << search.calls << ",\"output_gaps\":{";
    emit_activation_gap(out, "sw_percent", search.lower.sw_percent, search.upper.sw_percent);
    out << ',';
    emit_activation_gap(out, "activated_fraction", search.lower.activated_fraction, search.upper.activated_fraction);
    out << ',';
    emit_activation_gap(out, "ncact_raw", search.lower.ncact_raw, search.upper.ncact_raw);
    out << ',';
    emit_activation_gap(out, "ncact", search.lower.ncact, search.upper.ncact);
    out << ',';
    emit_activation_gap(out, "nc_after_activation", search.lower.nc_after_activation,
                        search.upper.nc_after_activation);
    out << ',';
    emit_activation_gap(out, "nccn_after_activation", search.lower.nccn_after_activation,
                        search.upper.nccn_after_activation);
    out << ',';
    emit_activation_gap(out, "nccn_final", search.lower.nccn_final, search.upper.nccn_final);
    out << ',';
    emit_activation_gap(out, "sw_ratio", search.lower.sw_ratio, search.upper.sw_ratio);
    out << ',';
    emit_activation_gap(out, "safe_pow_clamped_base_diagnostic", search.lower.safe_pow_clamped_base_diagnostic,
                        search.upper.safe_pow_clamped_base_diagnostic);
    out << ',';
    emit_activation_gap(out, "activation_fraction_pow", search.lower.activation_fraction_pow,
                        search.upper.activation_fraction_pow);
    out << ',';
    emit_activation_gap(out, "activation_fraction_one", search.lower.activation_fraction_one,
                        search.upper.activation_fraction_one);
    out << ',';
    emit_activation_gap(out, "activation_fraction_min_output", search.lower.activation_fraction_min_output,
                        search.upper.activation_fraction_min_output);
    out << ',';
    emit_activation_gap(out, "ncact_preclamp_fma", search.lower.ncact_preclamp_fma,
                        search.upper.ncact_preclamp_fma);
    out << ',';
    emit_activation_gap(out, "ncact_clamped_numerator", search.lower.ncact_clamped_numerator,
                        search.upper.ncact_clamped_numerator);
    out << ',';
    emit_activation_gap(out, "ncact_nccn_rate_cap", search.lower.ncact_nccn_rate_cap,
                        search.upper.ncact_nccn_rate_cap);
    out << ',';
    emit_activation_gap(out, "ncact_min_output", search.lower.ncact_min_output,
                        search.upper.ncact_min_output);
    out << ',';
    emit_activation_gap(out, "final_nc16", search.lower.final_nc16, search.upper.final_nc16);
    out << ',';
    emit_activation_gap(out, "final_nccn16", search.lower.final_nccn16, search.upper.final_nccn16);
    out << "},\"trace\":[";
    for (std::size_t i = 0; i < search.trace.size(); ++i) {
        if (i) out << ',';
        emit_activation_observation(out, search.trace[i]);
    }
    out << "]}";
}
const std::vector<std::string> activation_observable_names{
    "sw_percent", "activated_fraction", "ncact_raw", "ncact", "nc_after_activation",
    "nccn_after_activation", "nccn_final", "final_nc16", "final_nccn16",
    "sw_ratio", "safe_pow_clamped_base_diagnostic", "activation_fraction_pow",
    "activation_fraction_one", "activation_fraction_min_output", "ncact_preclamp_fma",
    "ncact_clamped_numerator", "ncact_nccn_rate_cap", "ncact_min_output",
};
const std::vector<std::string> activation_vjp_names{
    "sw_percent", "activated_fraction", "ncact_raw", "ncact", "nc_after_activation",
    "nccn_after_activation", "nccn_final", "final_nc16", "final_nccn16",
    "sw_ratio", "safe_pow_clamped_base_diagnostic", "activation_fraction_pow",
    "activation_fraction_min_output", "ncact_preclamp_fma", "ncact_clamped_numerator",
    "ncact_nccn_rate_cap", "ncact_min_output",
};
std::vector<Tensor> activation_observables(const Eval& e) {
    const auto& s = e.stages;
    return {
        s.at("fd_satadj_inner.sw_percent")[0][15],
        s.at("fd_satadj_inner.activated_fraction")[0][15],
        s.at("fd_satadj_inner.ncact_raw")[0][15],
        s.at("fd_satadj_inner.ncact")[0][15],
        s.at("fd_satadj_inner.nc_after_activation")[0][15],
        s.at("fd_satadj_inner.nccn_after_activation")[0][15],
        s.at("fd_satadj_inner.nccn_final")[0][15],
        e.final[8][15], e.final[7][15],
        s.at("fd_satadj_inner.sw_ratio")[0][15],
        s.at("fd_satadj_inner.safe_pow_clamped_base_diagnostic")[0][15],
        s.at("fd_satadj_inner.activation_fraction_pow")[0][15],
        s.at("fd_satadj_inner.activation_fraction_one")[0][15],
        s.at("fd_satadj_inner.activation_fraction_min_output")[0][15],
        s.at("fd_satadj_inner.ncact_preclamp_fma")[0][15],
        s.at("fd_satadj_inner.ncact_clamped_numerator")[0][15],
        s.at("fd_satadj_inner.ncact_nccn_rate_cap")[0][15],
        s.at("fd_satadj_inner.ncact_min_output")[0][15],
    };
}
std::vector<double> activation_observable_values(const Eval& e) {
    const auto obs = activation_observables(e);
    std::vector<double> out;
    out.reserve(obs.size());
    for (const auto& v : obs) out.push_back(*v.contiguous().to(torch::kCPU).data_ptr<double>());
    return out;
}
struct InteriorADPoint {
    double coordinate = 0.0;
    double th16 = 0.0, qv16 = 0.0;
    std::int64_t forward_call_ordinal = 0;
    std::vector<double> seed;
    std::vector<double> jvp;
    std::vector<double> values;
    std::vector<std::vector<double>> vjp_rows;
    Eval evaluation;
};
InteriorADPoint evaluate_activation_ad_point(const Input& in, const Map& map,
                                              BoundaryAxis axis, double coordinate,
                                              std::int64_t& forward_call_counter) {
    auto state = in.state;
    if (axis == BoundaryAxis::TH16) state[TH16] = coordinate;
    else state[QV16] = coordinate;
    auto x = torch::from_blob(state.data(), {STATE,K}, F64).clone().requires_grad_(true);
    Eval e = map(x, true);
    ++forward_call_counter;
    auto obs = activation_observables(e);
    auto packed_obs = torch::stack(obs);
    auto v = torch::zeros_like(x);
    if (axis == BoundaryAxis::TH16) v.reshape({STATE*K})[TH16] = 1.0;
    else v.reshape({STATE*K})[QV16] = state[QV16];
    InteriorADPoint out;
    out.coordinate = coordinate;
    out.th16 = state[TH16];
    out.qv16 = state[QV16];
    out.forward_call_ordinal = forward_call_counter;
    out.seed = values(v);
    out.jvp = values(double_reverse_jvp(packed_obs, x, v));
    out.values = activation_observable_values(e);
    out.evaluation = e;
    out.vjp_rows.reserve(activation_vjp_names.size());
    for (const auto& name : activation_vjp_names) {
        const auto it = std::find(activation_observable_names.begin(), activation_observable_names.end(), name);
        need(it != activation_observable_names.end(), "thermal VJP name not in observable list");
        const auto index = static_cast<std::size_t>(it - activation_observable_names.begin());
        const auto grad = torch::autograd::grad({obs[index]}, {x}, {}, true, false, false)[0];
        out.vjp_rows.push_back(values(grad));
    }
    return out;
}
bool same_activation_signature(const ActivationObservation& a, const ActivationObservation& b) {
    return a.sw_positive == b.sw_positive &&
           ((a.activated_fraction >= 1.0) == (b.activated_fraction >= 1.0)) &&
           a.ncact_cap_active == b.ncact_cap_active && a.ncact_cap_tie == b.ncact_cap_tie &&
           a.nccn_floor_active == b.nccn_floor_active && a.nccn_cap_active == b.nccn_cap_active;
}
bool same_operand_branch_signature(const ActivationObservation& a, const ActivationObservation& b) {
    return a.activation_fraction_pow_lt_one == b.activation_fraction_pow_lt_one &&
           a.activation_fraction_pow_eq_one == b.activation_fraction_pow_eq_one &&
           a.activation_fraction_pow_gt_one == b.activation_fraction_pow_gt_one &&
           a.ncact_raw_lt_nccn_rate_cap == b.ncact_raw_lt_nccn_rate_cap &&
           a.ncact_raw_eq_nccn_rate_cap == b.ncact_raw_eq_nccn_rate_cap &&
           a.ncact_raw_gt_nccn_rate_cap == b.ncact_raw_gt_nccn_rate_cap;
}
bool same_d1_signature(const ActivationObservation& a, const ActivationObservation& b) {
    return a.d1_warm == b.d1_warm && a.d1_snow_active == b.d1_snow_active &&
           a.d1_graupel_active == b.d1_graupel_active &&
           a.d1_psmlt_raw_candidate == b.d1_psmlt_raw_candidate &&
           a.d1_pgmlt_raw_candidate == b.d1_pgmlt_raw_candidate;
}
std::vector<double> one_sided_steps(BoundaryAxis axis, bool fraction_eq_one) {
    if (axis == BoundaryAxis::TH16) {
        return fraction_eq_one ? std::vector<double>{1.0e-4,1.0e-5,1.0e-6}
                               : std::vector<double>{1.0e-4,1.0e-5,1.0e-6,1.0e-7};
    }
    return fraction_eq_one ? std::vector<double>{1.0e-3,1.0e-4,1.0e-5,1.0e-6,1.0e-7}
                           : std::vector<double>{1.0e-5,1.0e-6,1.0e-7,1.0e-8};
}
void emit_interior_ad_point(std::ostream& out, const InteriorADPoint& point,
                            const Input& in, const Map& map, BoundaryAxis axis,
                            const char* side, std::int64_t& forward_call_counter) {
    auto base_obs = observe_activation(point.evaluation, in, axis, point.coordinate,
                                       BoundaryKind::OBSERVED_FRACTION_EQ_ONE);
    const std::string axis_name = axis == BoundaryAxis::TH16 ? "th16" : "qv16";
    base_obs.event_id = axis_name + "/" + side + "/interior_ad";
    base_obs.forward_call_ordinal = point.forward_call_ordinal;
    out << "{\"event_id\":\"" << base_obs.event_id << "\",\"forward_call_ordinal\":"
        << base_obs.forward_call_ordinal << ",\"input\":{";
    out << "\"th16\":" << std::setprecision(17) << point.th16
        << ",\"qv16\":" << point.qv16
        << ",\"physical_t16\":" << point.th16 * in.forcing[PII16]
        << ",\"coordinate_word\":\"" << word_fixed(point.coordinate) << "\"},\"branch\":";
    emit_activation_observation(out, base_obs);
    out << ",\"jvp\":{";
    for (std::size_t i = 0; i < activation_observable_names.size(); ++i) {
        if (i) out << ',';
        out << '"' << activation_observable_names[i] << "\":" << std::setprecision(17) << point.jvp[i];
    }
    out << "},\"vjp_rows\":{";
    for (std::size_t i = 0; i < activation_vjp_names.size(); ++i) {
        if (i) out << ',';
        const auto it = std::find(activation_observable_names.begin(), activation_observable_names.end(),
                                  activation_vjp_names[i]);
        need(it != activation_observable_names.end(), "thermal VJP name not in observable list");
        const auto jvp_index = static_cast<std::size_t>(it - activation_observable_names.begin());
        out << '"' << activation_vjp_names[i] << "\":{\"values\":";
        emit(out, point.vjp_rows[i]);
        out << ",\"raw_hex\":";
        emit_words(out, point.vjp_rows[i]);
        const double dot = dot_values(point.vjp_rows[i], point.seed);
        out << ",\"direction_vjp_dot\":" << dot
            << ",\"dot_minus_jvp\":" << dot - point.jvp[jvp_index] << '}';
    }
    out << "},\"one_sided_fd\":{\"coordinate_direction\":\"increasing\",\"step_scales\":[";
    const std::vector<double> steps = one_sided_steps(axis, base_obs.activated_fraction >= 1.0);
    for (std::size_t hi = 0; hi < steps.size(); ++hi) {
        if (hi) out << ',';
        const double h = steps[hi];
        auto endpoint_state = in.state;
        if (axis == BoundaryAxis::TH16) endpoint_state[TH16] = point.th16 + h;
        else endpoint_state[QV16] = point.qv16 * (1.0 + h);
        const double endpoint_coordinate = axis == BoundaryAxis::TH16
            ? endpoint_state[TH16] : endpoint_state[QV16];
        Eval endpoint_eval = activation_value_call(in, map, axis, endpoint_coordinate);
        ++forward_call_counter;
        auto endpoint_obs = observe_activation(endpoint_eval, in, axis, endpoint_coordinate,
                                               BoundaryKind::OBSERVED_FRACTION_EQ_ONE);
        std::ostringstream fd_id;
        fd_id << axis_name << '/' << side << "/fd/" << std::setprecision(8) << h;
        endpoint_obs.event_id = fd_id.str();
        endpoint_obs.forward_call_ordinal = forward_call_counter;
        const auto endpoint_values = activation_observable_values(endpoint_eval);
        const double parameter_gap = axis == BoundaryAxis::TH16
            ? endpoint_state[TH16] - point.th16 : endpoint_state[QV16] / point.qv16 - 1.0;
        out << "{\"event_id\":\"" << endpoint_obs.event_id
            << "\",\"forward_call_ordinal\":" << endpoint_obs.forward_call_ordinal
            << ",\"nominal_step\":" << std::setprecision(17) << h
            << ",\"represented_coordinate_gap\":" << endpoint_coordinate - point.coordinate
            << ",\"parameter_gap\":" << parameter_gap
            << ",\"same_activation_branch\":" << (same_activation_signature(base_obs, endpoint_obs) ? "true" : "false")
            << ",\"same_operand_branch\":" << (same_operand_branch_signature(base_obs, endpoint_obs) ? "true" : "false")
            << ",\"same_d1_branch\":" << (same_d1_signature(base_obs, endpoint_obs) ? "true" : "false")
            << ",\"endpoint\":";
        emit_activation_observation(out, endpoint_obs);
        out << ",\"outputs\":{";
        for (std::size_t i = 0; i < activation_observable_names.size(); ++i) {
            if (i) out << ',';
            const double fd = (endpoint_values[i] - point.values[i]) / parameter_gap;
            const auto distance = ulp_distance(endpoint_values[i], point.values[i]);
            out << '"' << activation_observable_names[i] << "\":{\"base\":" << point.values[i]
                << ",\"base_raw_hex\":\"" << word_fixed(point.values[i]) << "\""
                << ",\"endpoint\":" << endpoint_values[i] << ",\"fd\":" << fd
                << ",\"endpoint_raw_hex\":\"" << word_fixed(endpoint_values[i]) << "\""
                << ",\"ad_jvp\":" << point.jvp[i]
                << ",\"fd_minus_jvp\":" << fd - point.jvp[i]
                << ",\"output_ulp_distance\":" << distance
                << ",\"resolution_status\":\""
                << (distance <= 32 ? "unresolved_within_32_output_ulps" : "resolved_over_32_output_ulps")
                << "\"}";
        }
        out << "}}";
    }
    out << "]}}";
}
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
void run_activation_boundary(const Input& in, const Map& map, const Eval& baseline) {
    const double th0 = in.state[TH16];
    const double qv0 = in.state[QV16];
    const double pii = in.forcing[PII16];
    // Calls 0 and 1 are the mode-off and mode-on baseline forwards.
    // Each subsequent evaluation increments before emitting its ordinal.
    std::int64_t forward_call_counter = 1;
    const auto th_sw = bisect_activation_boundary(
        in, map, BoundaryAxis::TH16, BoundaryKind::SW_PERCENT_048, th0 + 1.0e-3, th0 + 1.0e-2,
        forward_call_counter);
    const auto th_cap = bisect_activation_boundary(
        in, map, BoundaryAxis::TH16, BoundaryKind::OBSERVED_FRACTION_EQ_ONE, th0 + 1.0e-3, th0 + 1.0e-2,
        forward_call_counter);
    const auto qv_sw = bisect_activation_boundary(
        in, map, BoundaryAxis::QV16, BoundaryKind::SW_PERCENT_048,
        qv0 * (1.0 - 1.0e-3), qv0 * (1.0 - 1.0e-4), forward_call_counter);
    const auto qv_cap = bisect_activation_boundary(
        in, map, BoundaryAxis::QV16, BoundaryKind::OBSERVED_FRACTION_EQ_ONE,
        qv0 * (1.0 - 1.0e-3), qv0 * (1.0 - 1.0e-4), forward_call_counter);
    const auto th_total = th_sw.calls + th_cap.calls;
    const auto qv_total = qv_sw.calls + qv_cap.calls;
    const double th_cap_input = th_cap.lower.predicate ? th_cap.lower.coordinate : th_cap.upper.coordinate;
    const double th_subcap_input = th_cap.lower.predicate ? th_cap.upper.coordinate : th_cap.lower.coordinate;
    const double th_outward = th_cap_input < th_subcap_input ? -1.0 : 1.0;
    const double th_fraction_eq_one = th_cap_input + th_outward * 1.0e-3;
    const double th_fraction_below_one = th_subcap_input - th_outward * 1.0e-3;
    const double qv_cap_input = qv_cap.lower.predicate ? qv_cap.lower.coordinate : qv_cap.upper.coordinate;
    const double qv_subcap_input = qv_cap.lower.predicate ? qv_cap.upper.coordinate : qv_cap.lower.coordinate;
    const double qv_outward = qv_cap_input < qv_subcap_input ? -1.0 : 1.0;
    const double qv_fraction_eq_one = qv_cap_input * (1.0 + qv_outward * 1.0e-4);
    const double qv_fraction_below_one = qv_subcap_input * (1.0 - qv_outward * 1.0e-4);
    const auto th_ad_on = evaluate_activation_ad_point(in, map, BoundaryAxis::TH16, th_fraction_eq_one,
                                                        forward_call_counter);
    const auto th_ad_off = evaluate_activation_ad_point(in, map, BoundaryAxis::TH16, th_fraction_below_one,
                                                         forward_call_counter);
    const auto qv_ad_on = evaluate_activation_ad_point(in, map, BoundaryAxis::QV16, qv_fraction_eq_one,
                                                        forward_call_counter);
    const auto qv_ad_off = evaluate_activation_ad_point(in, map, BoundaryAxis::QV16, qv_fraction_below_one,
                                                         forward_call_counter);
    need(stage_value(th_ad_on.evaluation.stages, "fd_satadj_inner.activated_fraction") >= 1.0,
         "TH fraction-eq-one interior point not on observed side");
    need(stage_value(th_ad_off.evaluation.stages, "fd_satadj_inner.activated_fraction") < 1.0,
         "TH fraction-below-one interior point not below observed boundary");
    need(stage_value(qv_ad_on.evaluation.stages, "fd_satadj_inner.activated_fraction") >= 1.0,
         "QV fraction-eq-one interior point not on observed side");
    need(stage_value(qv_ad_off.evaluation.stages, "fd_satadj_inner.activated_fraction") < 1.0,
         "QV fraction-below-one interior point not below observed boundary");
    constexpr std::size_t INTERIOR_AD_CALLS = 4;
    const std::size_t ONE_SIDED_FD_CALLS =
        one_sided_steps(BoundaryAxis::TH16, true).size() +
        one_sided_steps(BoundaryAxis::TH16, false).size() +
        one_sided_steps(BoundaryAxis::QV16, true).size() +
        one_sided_steps(BoundaryAxis::QV16, false).size();
    auto baseline_point = observe_activation(baseline, in, BoundaryAxis::TH16, th0,
                                             BoundaryKind::OBSERVED_FRACTION_EQ_ONE);
    baseline_point.event_id = "baseline";
    baseline_point.forward_call_ordinal = 1;
    std::cout << "{\"schema\":\"kdm6.native_d1_activation_boundary_operands.v1\",\"parent_schema\":\"kdm6.native_d1_activation_boundary.v1\",\"input\":{\"th16\":"
              << std::setprecision(17) << th0 << ",\"qv16\":" << qv0
              << ",\"pii16\":" << pii << ",\"physical_t16\":" << th0 * pii
              << ",\"th16_word\":\"" << word_fixed(th0)
              << "\",\"qv16_word\":\"" << word_fixed(qv0)
              << "\",\"dt\":" << in.dt << ",\"xland\":" << in.xland
              << ",\"packed_indices\":{\"th16\":" << TH16 << ",\"qv16\":" << QV16 << "}},\"thresholds\":{\"sw_percent\":0.48,\"observed_activated_fraction_limit\":1.0},\"baseline\":";
    emit_activation_observation(std::cout, baseline_point);
    std::cout << ",\"call_counts\":{\"baseline_off_on\":2,\"value_only_bisection_forward_calls\":"
              << th_total + qv_total << ",\"interior_ad_forward_calls\":" << INTERIOR_AD_CALLS
              << ",\"one_sided_fd_value_only_forward_calls\":" << ONE_SIDED_FD_CALLS
              << ",\"th16_bisection_calls\":" << th_total
              << ",\"qv16_bisection_calls\":" << qv_total
              << ",\"total_full_call_forwards\":" << 2 + th_total + qv_total + INTERIOR_AD_CALLS + ONE_SIDED_FD_CALLS
              << "},\"axes\":{";
    std::cout << "\"th16\":{\"coordinate_kind\":\"absolute potential-temperature K\",\"bracket_seed\":{\"fraction_eq_one\":"
              << th0 + 1.0e-3 << ",\"fraction_below_one\":" << th0 + 1.0e-2 << "},\"bisection\":{\"sw_percent_0p48\":";
    emit_boundary_search(std::cout, th_sw);
    std::cout << ",\"activated_fraction_ge_1_observed_value\":";
    emit_boundary_search(std::cout, th_cap);
    std::cout << "},\"interior_points\":{\"fraction_eq_one\":";
    emit_interior_ad_point(std::cout, th_ad_on, in, map, BoundaryAxis::TH16,
                           "fraction_eq_one", forward_call_counter);
    std::cout << ",\"fraction_below_one\":";
    emit_interior_ad_point(std::cout, th_ad_off, in, map, BoundaryAxis::TH16,
                           "fraction_below_one", forward_call_counter);
    std::cout << "}},\"qv16\":{\"coordinate_kind\":\"relative water-vapor mixing ratio\",\"bracket_seed\":{\"fraction_below_one\":"
              << qv0 * (1.0 - 1.0e-3) << ",\"fraction_eq_one\":" << qv0 * (1.0 - 1.0e-4)
              << "},\"bisection\":{\"sw_percent_0p48\":";
    emit_boundary_search(std::cout, qv_sw);
    std::cout << ",\"activated_fraction_ge_1_observed_value\":";
    emit_boundary_search(std::cout, qv_cap);
    std::cout << "},\"interior_points\":{\"fraction_eq_one\":";
    emit_interior_ad_point(std::cout, qv_ad_on, in, map, BoundaryAxis::QV16,
                           "fraction_eq_one", forward_call_counter);
    std::cout << ",\"fraction_below_one\":";
    emit_interior_ad_point(std::cout, qv_ad_off, in, map, BoundaryAxis::QV16,
                           "fraction_below_one", forward_call_counter);
    std::cout << "}}}}\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        const bool activation_boundary_mode = argc == 3 && std::string(argv[2]) == "--activation-boundary";
        need(argc == 2 || activation_boundary_mode,
             "usage: native_pre2_input_ad INPUT_BIN [--activation-boundary]");
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
        if (activation_boundary_mode) {
            run_activation_boundary(in, map, on);
            return 0;
        }
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
