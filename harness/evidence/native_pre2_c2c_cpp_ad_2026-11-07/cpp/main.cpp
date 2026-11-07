// Conditional native-16 pre2 ProgB -> slope -> C2c -> NC-budget f64 AD.
// Scalar extraction is restricted to value reporting after graph evaluation.
#include "kdm6/progb.h"
#include "kdm6/slope.h"
#include "kdm6/cold.h"
#include "kdm6/ops.h"

#include <torch/torch.h>
#include <torch/csrc/autograd/autograd.h>

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
#include <vector>

namespace {
using torch::Tensor;
const auto F64 = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);

void need(bool ok, const std::string& why) {
    if (!ok) throw std::runtime_error(why);
}
std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> out;
    std::stringstream stream(s);
    std::string part;
    while (std::getline(stream, part, sep)) out.push_back(part);
    return out;
}
double from_word(const std::string& raw) {
    const auto bits = static_cast<std::uint64_t>(std::stoull(raw, nullptr, 16));
    double value;
    static_assert(sizeof(bits) == sizeof(value), "binary64 required");
    std::memcpy(&value, &bits, sizeof(value));
    need(std::isfinite(value), "nonfinite selected operand");
    return value;
}
std::string word(double value) {
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    std::ostringstream out;
    out << std::hex << bits;
    return out.str();
}
struct Inputs {
    std::map<std::string, double> fields;
    explicit Inputs(const std::string& path) {
        std::ifstream in(path);
        need(static_cast<bool>(in), "capture unavailable");
        std::string line;
        need(static_cast<bool>(std::getline(in, line)), "capture header absent");
        need(line == "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex",
             "capture columns changed");
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            const auto cell = split(line, ',');
            need(cell.size() == 11, "capture row shape");
            if (cell[4] != "23") continue;  // native level 16, top-first index
            need((cell[0] == "0" || cell[0] == "1") && cell[1] == "1" && cell[3] == "0"
                 && cell[5] == "1" && cell[6] == "39", "selected call identity");
            if (cell[9] != "f64") continue;
            const auto key = cell[7] + "/" + cell[8];
            need(fields.emplace(key, from_word(cell[10])).second, "duplicate selected operand");
        }
    }
    double get(const char* stage, const char* name) const {
        const auto key = std::string(stage) + "/" + name;
        const auto it = fields.find(key);
        need(it != fields.end(), "missing selected operand: " + key);
        return it->second;
    }
};
Tensor scalar(double x) { return torch::full({1, 1}, x, F64); }
std::vector<double> values(const Tensor& tensor) {
    auto flat = tensor.contiguous().to(torch::kCPU);
    const auto* ptr = flat.data_ptr<double>();
    return {ptr, ptr + flat.numel()};
}
void emit(std::ostream& out, const std::vector<double>& x) {
    out << '[';
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (i) out << ',';
        out << std::setprecision(17) << x[i];
    }
    out << ']';
}
void emit_words(std::ostream& out, const std::vector<double>& x) {
    out << '[';
    for (std::size_t i = 0; i < x.size(); ++i) {
        if (i) out << ',';
        out << '"' << word(x[i]) << '"';
    }
    out << ']';
}

struct ConditionalMap {
    const Inputs& data;
    const kdm6::progb::ProgBParams pg_params = kdm6::progb::default_progb_params();
    const kdm6::slope::SlopeParams sl_params = kdm6::slope::default_slope_params();

    Tensor operator()(const Tensor& x) const {
        need(x.sizes() == torch::IntArrayRef({2}) && x.scalar_type() == torch::kFloat64,
             "f64[2] pre2 QG/BRS required");
        const auto qg = x[0].reshape({1, 1});
        const auto brs = x[1].reshape({1, 1});
        const auto fix = [&](const char* field) { return scalar(data.get("c2c_number_inputs", field)); };
        const auto pg = kdm6::progb::progb_param_torch(
            qg, brs, pg_params, torch::kFloat64, /*midpoint_trace=*/false);
        // Other species are fixed, numerically safe placeholders. The graupel
        // slope subpath depends on qg/dend and the ProgB outputs below.
        kdm6::slope::SlopeKdm6Inputs si{
            scalar(data.get("nracw_producer", "qr")), fix("qs"), qg, scalar(1.0e-10),
            scalar(data.get("nracw_producer", "nr")), scalar(1.0),
            scalar(data.get("pre2_producer", "dend_input")), fix("denfac"), scalar(274.6),
            pg.pidn0g, pg.pvtg, pg.bvtg, pg.rslopegbmax,
        };
        const auto sl = kdm6::slope::slope_kdm6_torch(si, sl_params);
        auto cp = kdm6::cold::default_cloud_water_riming_params();
        cp.ncmin_tensor = fix("ncmin");
        kdm6::cold::CloudWaterRimingInputs ci{
            fix("qc"), fix("nc"), fix("qs"), qg, scalar(1.0e-10),
            fix("den"), fix("denfac"), fix("n0so"), fix("n0go"),
            scalar(1.0e5), fix("n0c"), fix("n0sfac"), pg.avtg, pg.g3pbg,
            scalar(1.0e-4), scalar(-1.0),
            fix("rslope3_s"), fix("rslopeb_s"), fix("rslopemu_s"),
            sl.rslope3_g, sl.rslopeb_g, sl.rslopemu_g,
            scalar(1.0e-4), scalar(1.0e-4), scalar(1.0),
            fix("rslopec"), fix("rslopecmu"),
        };
        const auto c2c = kdm6::cold::cloud_water_riming_torch(
            ci, cp, data.get("c2c_number_inputs", "dtcld"));
        const auto budget = [&](const char* name) { return scalar(data.get("nc_budget", name)); };
        const auto rate = -budget("nraut") - budget("nccol") - budget("nracw")
            - budget("niacw") * budget("cold_mask") - c2c.naacw - c2c.naacw;
        const auto amount = -budget("ninuc") - budget("nfrzdtc") + budget("pimlt_ni");
        const auto nc_raw = kdm6::ops::fma_acc(budget("nc_before") + amount,
                                               rate, scalar(data.get("nc_budget", "dtcld")));
        const auto nc = torch::clamp(nc_raw, /*min=*/0.0);
        return torch::stack({
            pg.rhox.reshape({}), pg.bg.reshape({}), pg.avtg.reshape({}),
            pg.bvtg.reshape({}), pg.g3pbg.reshape({}), pg.pidn0g.reshape({}),
            sl.rslope3_g.reshape({}), sl.rslopeb_g.reshape({}),
            c2c.nsacw.reshape({}), c2c.ngacw.reshape({}), c2c.naacw.reshape({}),
            nc.reshape({}),
        });
    }
};

Tensor double_reverse_jvp(const Tensor& y, const Tensor& x, const Tensor& v) {
    auto u = torch::zeros_like(y).requires_grad_(true);
    auto jt_u = torch::autograd::grad({(y * u).sum()}, {x}, {}, true, true, false)[0];
    return torch::autograd::grad({(jt_u * v).sum()}, {u}, {}, true, false, false)[0];
}
}  // namespace

int main(int argc, char** argv) {
    try {
        need(argc == 2, "usage: native_pre2_c2c_cpp_ad CAPTURE_CSV");
        torch::set_num_threads(1);
        const Inputs data(argv[1]);
        const ConditionalMap map{data};
        auto x = torch::tensor({data.get("pre2_producer", "qg_input"),
                                data.get("pre2_producer", "brs_input")}, F64).requires_grad_(true);
        const auto y = map(x);
        const auto baseline = values(y);
        const std::vector<std::string> names = {"rho", "brs", "avtg", "bvtg", "g3pbg", "pidn0g",
                                                 "rslope3_g", "rslopeb_g", "nsacw", "ngacw", "naacw", "nc_budget"};
        std::vector<std::vector<double>> jacobian;
        for (std::int64_t i = 0; i < y.numel(); ++i) {
            auto grad = torch::autograd::grad({y[i]}, {x}, {}, true, false, false)[0];
            jacobian.push_back(values(grad));
        }
        const std::vector<std::pair<std::string, std::vector<double>>> dirs = {
            {"qg_relative", {data.get("pre2_producer", "qg_input"), 0.0}},
            {"brs_relative", {0.0, data.get("pre2_producer", "brs_input")}},
            {"joint_relative", {data.get("pre2_producer", "qg_input"),
                                 data.get("pre2_producer", "brs_input")}},
        };
        std::cout << "{\"schema\":\"kdm6.native_pre2_c2c_cpp_ad.v1\",\"output_order\":[";
        for (std::size_t i = 0; i < names.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << '"' << names[i] << '"';
        }
        std::cout << "],\"baseline\":{\"values\":";
        emit(std::cout, baseline);
        std::cout << ",\"raw_hex\":";
        emit_words(std::cout, baseline);
        std::cout << "},\"vjp_rows\":{\n";
        for (std::size_t i = 0; i < names.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << '"' << names[i] << "\":";
            emit(std::cout, jacobian[i]);
        }
        std::cout << "},\"directions\":{";
        for (std::size_t di = 0; di < dirs.size(); ++di) {
            if (di) std::cout << ',';
            const auto& [name, seed] = dirs[di];
            auto v = torch::tensor(seed, F64);
            const auto jvp = values(double_reverse_jvp(y, x, v));
            std::cout << '"' << name << "\":{\"seed\":";
            emit(std::cout, seed);
            std::cout << ",\"jvp\":";
            emit(std::cout, jvp);
            std::cout << ",\"finite_differences\":{";
            const std::vector<double> steps = name == "joint_relative"
                ? std::vector<double>{1.0e-3, 1.0e-5, 1.0e-6, 1.0e-7}
                : std::vector<double>{1.0e-4, 1.0e-5, 1.0e-6, 1.0e-7};
            const auto center = values(x);
            for (std::size_t hi = 0; hi < steps.size(); ++hi) {
                if (hi) std::cout << ',';
                const double h = steps[hi];
                auto high_x = center, low_x = center;
                for (int k = 0; k < 2; ++k) {
                    high_x[k] += seed[k] * h;
                    low_x[k] -= seed[k] * h;
                }
                const auto high = values(map(torch::tensor(high_x, F64)));
                const auto low = values(map(torch::tensor(low_x, F64)));
                std::cout << '"' << std::setprecision(8) << h << "\":{\"high_input\":";
                emit(std::cout, high_x);
                std::cout << ",\"low_input\":";
                emit(std::cout, low_x);
                std::cout << ",\"high\":";
                emit(std::cout, high);
                std::cout << ",\"low\":";
                emit(std::cout, low);
                std::cout << '}';
            }
            std::cout << "}}";
        }
        std::cout << "}}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "NATIVE_PRE2_C2C_CPP_AD_FAILED: " << e.what() << '\n';
        return 1;
    }
}
