// Value-only report of an actual C++/libtorch graph for the selected native
// entry work2/ProgB -> D1 melt -> inline stores -> postmelt ProgB conditional map. Scalar extraction
// occurs only after graph and derivative evaluation; it never feeds AD inputs.
#include "kdm6/coordinator.h"
#include "kdm6/melt_freeze.h"
#include "kdm6/progb.h"
#include "kdm6/slope.h"
#include "kdm6/thermo.h"

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

#ifdef KDM6_CAPTURE_VARIANT
// The frozen native capture overlay adds a value-only checkpoint label to this
// function signature. All arithmetic is identical to the public 5-arg form.
namespace kdm6 {
CoordinatorState apply_melt_freeze_inline(
    const CoordinatorState&, const MeltFreezePhaseOutputs&,
    const PreambleCore&, double, double, const char*);
}
#endif

namespace {
using torch::Tensor;
using kdm6::CoordinatorState;

void require(bool ok, const std::string& why) {
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
    static_assert(sizeof(bits) == sizeof(value), "binary64 words required");
    std::memcpy(&value, &bits, sizeof(value));
    require(std::isfinite(value), "nonfinite selected operand");
    return value;
}

std::string word(double value) {
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    std::ostringstream out;
    out << std::hex << bits;
    return out.str();
}

struct InputWords {
    std::map<std::string, double> fields;

    explicit InputWords(const std::string& path) {
        std::ifstream in(path);
        require(static_cast<bool>(in), "capture input unavailable");
        std::string line;
        require(static_cast<bool>(std::getline(in, line)), "capture header absent");
        require(line == "one_step_call,runtime_call,substep,b_zero,k_zero,B,K,stage,field,dtype,raw_hex",
                "capture columns changed");
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            const auto cell = split(line, ',');
            require(cell.size() == 11, "capture row shape");
            if (cell[4] != "23") continue;  // native level 16, top-first index
            require(cell[0] == "2" && cell[1] == "2" && cell[3] == "27945"
                    && cell[5] == "32248" && cell[6] == "39", "selected call identity");
            if (cell[9] != "f64") continue;
            const auto key = cell[7] + "/" + cell[8];
            require(fields.emplace(key, from_word(cell[10])).second, "duplicate selected operand");
        }
    }

    double get(const char* stage, const char* name) const {
        const auto key = std::string(stage) + "/" + name;
        const auto it = fields.find(key);
        require(it != fields.end(), "missing selected operand: " + key);
        return it->second;
    }
};

const auto F64 = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);

Tensor scalar(double value) { return torch::full({1, 1}, value, F64); }

struct ConditionalMap {
    const InputWords& data;
    const kdm6::thermo::ThermoParams thermo = kdm6::thermo::default_thermo_params();
    const kdm6::progb::ProgBParams prog = kdm6::progb::default_progb_params();
    const kdm6::slope::SlopeParams slope_params = kdm6::slope::default_slope_params();

    Tensor operator()(const Tensor& x) const {
        require(x.sizes() == torch::IntArrayRef({6}) && x.scalar_type() == torch::kFloat64,
                "input vector must be f64[6]");
        const auto qv = x[0].reshape({1, 1});
        const auto t = x[1].reshape({1, 1});
        const auto qg = x[2].reshape({1, 1});
        const auto brs_pre = x[3].reshape({1, 1});
        const auto p = x[4].reshape({1, 1});
        const auto qs = x[5].reshape({1, 1});
        const auto den = scalar(data.get("d1_upstream_entry", "den"));
        const auto dend = scalar(data.get("d1_upstream_entry", "dend"));
        const auto cpm = kdm6::thermo::compute_cpm(qv, thermo);
        const auto xl = kdm6::thermo::compute_xl(t, thermo);
        const auto supcol = kdm6::thermo::compute_supcol(t, thermo);
        const auto work2 = kdm6::thermo::compute_work2_venfac(p, t, den, thermo);
        const auto entry_progb = kdm6::progb::progb_param_torch(
            qg, brs_pre, prog, torch::kFloat64, /*midpoint_trace=*/false);
        const kdm6::slope::SlopeKdm6Inputs slope_in{
            scalar(data.get("d1_state_entry", "qr")), qs, qg,
            scalar(data.get("d1_melt_producer", "qi")),
            scalar(data.get("d1_state_entry", "nr")),
            scalar(data.get("d1_melt_producer", "ni")),
            dend, kdm6::thermo::compute_denfac(den, thermo), t,
            entry_progb.pidn0g, entry_progb.pvtg, entry_progb.bvtg,
            entry_progb.rslopegbmax,
        };
        const auto slope_out = kdm6::slope::slope_kdm6_torch(slope_in, slope_params);
        CoordinatorState s{
            qv,
            scalar(data.get("c3_pre_mf_d1", "qc_before")),
            scalar(data.get("d1_state_entry", "qr")),
            qs,
            qg,
            scalar(data.get("d1_melt_producer", "qi")),
            scalar(data.get("c3_pre_mf_d1", "nc_before")),
            scalar(data.get("d1_state_entry", "nr")),
            scalar(data.get("d1_melt_producer", "ni")),
            scalar(0.0),
            entry_progb.bg,
            t,
        };
        const auto m = [&](const char* field) {
            return scalar(data.get("d1_melt_producer", field));
        };
        kdm6::melt::MeltingInputs mi{
            s.qs, s.qg, s.qi, s.ni,
            s.t, p, den, entry_progb.rhox,
            cpm, m("n0so"), m("n0go"), slope_out.n0sfac_field,
            work2, entry_progb.precg2,
            slope_out.rslope_s, slope_out.rslope2_s, slope_out.rslopeb_s, slope_out.rslopemu_s,
            slope_out.rslope_g, slope_out.rslope2_g, slope_out.rslopeb_g, slope_out.rslopemu_g,
        };
        const kdm6::melt::MeltingParams mp{
            data.get("d1_melt_producer", "precs1"),
            data.get("d1_melt_producer", "precs2"),
            data.get("d1_melt_producer", "precg1"),
            data.get("d1_melt_producer", "xlf"),
            data.get("d1_melt_producer", "t0c"),
            data.get("d1_melt_producer", "qcrmin"),
        };
        const double dt = data.get("d1_melt_producer", "dtcld");
        auto melt = kdm6::melt::melting_torch(
            mi, mp, dt, m("mass_den"), /*midpoint_trace=*/false);
        const auto zero = torch::zeros_like(qv);
        kdm6::MeltFreezePhaseOutputs mf{};
        mf.psmlt = melt.psmlt;
        mf.pgmlt = melt.pgmlt;
        mf.pimlt_qi = melt.pimlt_qi;
        mf.pimlt_ni = melt.pimlt_ni;
        mf.sfac_melt = melt.sfac;
        mf.gfac_melt = melt.gfac;
        mf.delta_brs_melt = melt.delta_brs;
        mf.psmlt_capped = melt.psmlt_capped;
        mf.pgmlt_capped = melt.pgmlt_capped;
        mf.delta_brs_capped = melt.delta_brs_capped;
        mf.pinuc = zero; mf.ninuc = zero;
        mf.pfrzdtc = zero; mf.nfrzdtc = zero;
        mf.pfrzdtr = zero; mf.nfrzdtr = zero;
        mf.delta_brs_freeze = zero;
        mf.pseml = zero; mf.nseml = zero;
        mf.pgeml = zero; mf.ngeml = zero;
        const kdm6::PreambleCore pre{cpm, xl, supcol, entry_progb.rhox};
#ifdef KDM6_CAPTURE_VARIANT
        auto d1 = kdm6::apply_melt_freeze_inline(s, mf, pre, dt, thermo.xls, "d1");
#else
        auto d1 = kdm6::apply_melt_freeze_inline(s, mf, pre, dt, thermo.xls);
#endif
        auto reslope = kdm6::progb::progb_param_torch(
            d1.qg, d1.brs, prog, torch::kFloat64, /*midpoint_trace=*/false);
        return torch::stack({
            work2.reshape({}), entry_progb.precg2.reshape({}),
            entry_progb.rhox.reshape({}), entry_progb.bg.reshape({}),
            entry_progb.avtg.reshape({}), entry_progb.bvtg.reshape({}),
            melt.psmlt_capped.reshape({}), melt.pgmlt_capped.reshape({}),
            d1.qg.reshape({}), d1.brs.reshape({}), d1.nr.reshape({}),
            reslope.rhox.reshape({}), reslope.bg.reshape({}),
            reslope.avtg.reshape({}), reslope.bvtg.reshape({}), d1.t.reshape({}),
            slope_out.n0sfac_field.reshape({}),
            slope_out.rslope_s.reshape({}), slope_out.rslope2_s.reshape({}),
            slope_out.rslopeb_s.reshape({}), slope_out.rslopemu_s.reshape({}),
            slope_out.rslope_g.reshape({}), slope_out.rslope2_g.reshape({}),
            slope_out.rslopeb_g.reshape({}), slope_out.rslopemu_g.reshape({}),
        });
    }
};

std::vector<double> values(const Tensor& t) {
    auto flat = t.contiguous().to(torch::kCPU);
    const auto* p = flat.data_ptr<double>();
    return {p, p + flat.numel()};
}

void emit_array(std::ostream& out, const std::vector<double>& x) {
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

Tensor double_reverse_jvp(const Tensor& y, const Tensor& x, const Tensor& v) {
    // Same reverse-over-reverse identity as the production Handle::jvp.
    auto u = torch::zeros_like(y).requires_grad_(true);
    auto scalar = (y * u).sum();
    auto jt_u = torch::autograd::grad(
        {scalar}, {x}, {}, /*retain_graph=*/true, /*create_graph=*/true,
        /*allow_unused=*/false)[0];
    auto inner = (jt_u * v).sum();
    return torch::autograd::grad(
        {inner}, {u}, {}, /*retain_graph=*/true, /*create_graph=*/false,
        /*allow_unused=*/false)[0];
}

struct Direction {
    const char* name;
    int index;
    double seed;
    std::vector<double> half_steps;
};

}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: native_d1_slope_cpp_ad CAPTURE_CSV");
        torch::set_num_threads(1);
        const InputWords input(argv[1]);
        const ConditionalMap map{input};
        const auto options = torch::TensorOptions().dtype(torch::kFloat64);
        auto x = torch::tensor({
            input.get("d1_upstream_entry", "qv"),
            input.get("d1_upstream_entry", "t"),
            input.get("d1_upstream_entry", "qg"),
            input.get("d1_upstream_entry", "brs"),
            input.get("d1_upstream_entry", "p"),
            input.get("d1_melt_producer", "qs"),
        }, options).requires_grad_(true);
        auto y = map(x);
        const auto base = values(y);
        const auto weights = torch::tensor(
            {2.0, -3.0, 5.0, 7.0, -11.0, 13.0, -17.0, 19.0,
             -23.0, 29.0, -31.0, 37.0, -41.0, 43.0, -47.0, 53.0,
             -59.0, 61.0, -67.0, 71.0, -73.0, 79.0, -83.0, 89.0, -97.0}, options);
        auto gx = torch::autograd::grad(
            {(y * weights).sum()}, {x}, {}, /*retain_graph=*/true,
            /*create_graph=*/false, /*allow_unused=*/false)[0];
        const std::vector<Direction> directions = {
            {"relative_qv16", 0, input.get("d1_upstream_entry", "qv"), {0.1, 0.01, 0.001}},
            {"absolute_t16", 1, 1.0, {0.1, 0.01, 0.001}},
            {"relative_qg16", 2, input.get("d1_upstream_entry", "qg"), {1e-5, 1e-6, 1e-7}},
            {"relative_brs_pre16", 3, input.get("d1_upstream_entry", "brs"), {1e-5, 1e-6, 1e-7}},
            {"relative_p16", 4, input.get("d1_upstream_entry", "p"), {0.01, 0.001, 0.0001}},
            {"relative_qs16", 5, input.get("d1_melt_producer", "qs"), {0.01, 0.001, 0.0001}},
        };

        std::cout << "{\"schema\":\"kdm6.native_d1_slope_cpp_ad.v1\",\"output_order\":["
                     "\"work2\",\"entry_precg2\",\"entry_rhox\",\"entry_brs\","
                     "\"entry_avtg\",\"entry_bvtg\",\"ps\",\"pg\",\"qg_d1\","
                     "\"brs_d1\",\"nr_d1\",\"rhox\",\"brs_reclamped\","
                     "\"avtg\",\"bvtg\",\"t_d1\","
                     "\"n0sfac\",\"rslope_s\",\"rslope2_s\",\"rslopeb_s\",\"rslopemu_s\","
                     "\"rslope_g\",\"rslope2_g\",\"rslopeb_g\",\"rslopemu_g\"],";
        std::cout << "\"baseline\":{\"values\":";
        emit_array(std::cout, base);
        std::cout << ",\"raw_hex\":";
        emit_words(std::cout, base);
        std::cout << "},\"directions\":{";
        for (std::size_t d = 0; d < directions.size(); ++d) {
            const auto& dir = directions[d];
            if (d) std::cout << ',';
            auto v = torch::zeros_like(x);
            v[dir.index] = dir.seed;  // value-only direction seed, not a graph input
            const auto jv_tensor = double_reverse_jvp(y, x, v);
            const auto jv = values(jv_tensor);
            const auto vjp_dot = (gx * v).sum().item<double>();
            const auto jvp_dot = (jv_tensor * weights).sum().item<double>();
            std::cout << '"' << dir.name << "\":{\"seed\":" << std::setprecision(17) << dir.seed
                      << ",\"jvp\":";
            emit_array(std::cout, jv);
            std::cout << ",\"vjp_dot\":" << std::setprecision(17) << vjp_dot
                      << ",\"jvp_dot\":" << std::setprecision(17) << jvp_dot
                      << ",\"finite_differences\":{";
            for (std::size_t j = 0; j < dir.half_steps.size(); ++j) {
                const double h = dir.half_steps[j];
                if (j) std::cout << ',';
                auto up = values(x);
                auto lo = up;
                up[dir.index] += dir.seed * h;
                lo[dir.index] -= dir.seed * h;
                const auto high = values(map(torch::tensor(up, options)));
                const auto low = values(map(torch::tensor(lo, options)));
                const double gap = (up[dir.index] - lo[dir.index]) / dir.seed;
                std::vector<double> fd(high.size());
                for (std::size_t i = 0; i < fd.size(); ++i) fd[i] = (high[i] - low[i]) / gap;
                std::cout << '"' << std::setprecision(8) << h << "\":{\"gap\":"
                          << std::setprecision(17) << gap << ",\"high\":";
                emit_array(std::cout, high);
                std::cout << ",\"low\":";
                emit_array(std::cout, low);
                std::cout << ",\"fd\":";
                emit_array(std::cout, fd);
                std::cout << '}';
            }
            std::cout << "}}";
        }
        std::cout << "},\"qg_cross_cap\":{";
        auto up = values(x);
        auto lo = up;
        up[2] *= 1.0001;
        lo[2] *= 0.9999;
        const auto high = values(map(torch::tensor(up, options)));
        const auto low = values(map(torch::tensor(lo, options)));
        std::cout << "\"high\":";
        emit_array(std::cout, high);
        std::cout << ",\"low\":";
        emit_array(std::cout, low);
        std::cout << "}}\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "NATIVE_D1_SLOPE_CPP_AD_FAILED: " << exc.what() << '\n';
        return 1;
    }
}
