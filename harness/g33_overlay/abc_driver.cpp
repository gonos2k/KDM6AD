// C++ A/B/C non-invasiveness driver for the G3.3-M diagnostic overlay.
//
// One executable is linked against the canonical archive (A); a second is linked
// with all four diagnostic overlay objects replacing their canonical archive
// members (B/C). The diagnostic executable is run twice: env absent (B), then
// sealed dump env active (C). `fourcase_v1` is generated from the same raw-bit
// authority as the standalone Fortran driver.
#include "kdm6/constants.h"
#include "kdm6/runtime.h"
#include "kdm6/state.h"
#include "g33_fixture_v1.h"

#include <torch/torch.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

using kdm6::Forcing;
using kdm6::PhysicsOptions;
using kdm6::PhysicsVariant;
using kdm6::State;

struct Fixture {
    State state;
    Forcing forcing;
    c10::optional<torch::Tensor> xland;
    int64_t B;
    int64_t K;
    double dt;
    double ncmin_land;
    double ncmin_sea;
};

float f32_from_bits(std::uint32_t bits) {
    float value;
    std::memcpy(&value, &bits, sizeof value);
    return value;
}

std::uint32_t bits_from_f32(float value) {
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof bits);
    return bits;
}

torch::Tensor tensor2(int64_t B, int64_t K, const std::vector<float>& values) {
    if (static_cast<int64_t>(values.size()) != B * K)
        throw std::runtime_error("fixture tensor has the wrong element count");
    return torch::tensor(values, torch::TensorOptions().dtype(torch::kFloat32))
        .reshape({B, K});
}

torch::Tensor tensor1(const std::vector<float>& values) {
    return torch::tensor(values, torch::TensorOptions().dtype(torch::kFloat32));
}

template <std::size_t N>
std::vector<float> decode(const std::array<std::uint32_t, N>& words) {
    std::vector<float> values;
    values.reserve(N);
    for (auto word : words) values.push_back(f32_from_bits(word));
    return values;
}

Fixture make_shared_fixture() {
    namespace fx = g33_fixture_v1;
    State s;
    s.th = tensor2(fx::B, fx::K, decode(fx::th_bits));
    s.qv = tensor2(fx::B, fx::K, decode(fx::qv_bits));
    s.qc = tensor2(fx::B, fx::K, decode(fx::qc_bits));
    s.qr = tensor2(fx::B, fx::K, decode(fx::qr_bits));
    s.qi = tensor2(fx::B, fx::K, decode(fx::qi_bits));
    s.qs = tensor2(fx::B, fx::K, decode(fx::qs_bits));
    s.qg = tensor2(fx::B, fx::K, decode(fx::qg_bits));
    s.nccn = tensor2(fx::B, fx::K, decode(fx::nccn_bits));
    s.nc = tensor2(fx::B, fx::K, decode(fx::nc_bits));
    s.ni = tensor2(fx::B, fx::K, decode(fx::ni_bits));
    s.nr = tensor2(fx::B, fx::K, decode(fx::nr_bits));
    s.bg = tensor2(fx::B, fx::K, decode(fx::bg_bits));

    Forcing f;
    f.rho = tensor2(fx::B, fx::K, decode(fx::rho_bits));
    f.p = tensor2(fx::B, fx::K, decode(fx::p_bits));
    f.pii = tensor2(fx::B, fx::K, decode(fx::pii_bits));
    f.delz = tensor2(fx::B, fx::K, decode(fx::delz_bits));

    const float qmin = static_cast<float>(kdm6::constants::EPS);
    if (bits_from_f32(qmin) != fx::qmin_bits)
        throw std::runtime_error("shared fixture qmin differs from kdm6::constants::EPS");
    return Fixture{
        std::move(s), std::move(f), tensor1(decode(fx::xland_bits)), fx::B, fx::K,
        f32_from_bits(fx::dt_bits), f32_from_bits(fx::ncmin_land_bits),
        f32_from_bits(fx::ncmin_sea_bits)};
}

Fixture make_fixture(const std::string& name) {
    if (name == "fourcase_v1") return make_shared_fixture();

    const int64_t K = 4;
    const int64_t B = name == "closure3" ? 3 : 4;
    if (name != "closure3" && name != "species_iso")
        throw std::runtime_error("case must be closure3, species_iso, or fourcase_v1");

    std::vector<float> th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg;
    std::vector<float> rho, pii, p, delz;
    for (int64_t b = 0; b < B; ++b) {
        for (int64_t k = 0; k < K; ++k) {
            const float layer = 1.0f - 0.12f * static_cast<float>(k);
            const float temperature = name == "closure3"
                ? (b == 0 ? 290.0f : (b == 1 ? 268.0f : 242.0f))
                : (b == 0 ? 290.0f : (b == 1 ? 273.5f : (b == 2 ? 268.0f : 242.0f)));
            th.push_back(temperature - 0.5f * static_cast<float>(k));
            qv.push_back(1.0e-3f + 2.0e-5f * static_cast<float>(b));
            qc.push_back(1.0e-6f * (1.0f + 0.1f * static_cast<float>(k)));
            nccn.push_back(1.0e9f);
            nc.push_back(1.0e8f);

            float v_qr = 0.0f, v_qi = 0.0f, v_qs = 0.0f, v_qg = 0.0f;
            float v_nr = 0.0f, v_ni = 0.0f;
            if (name == "closure3") {
                if (b == 0) {
                    v_qr = 4.0e-5f * layer; v_nr = 1.0e5f * layer;
                } else if (b == 1) {
                    v_qr = 2.0e-5f * layer; v_nr = 5.0e4f * layer;
                    v_qi = 2.0e-5f * layer; v_ni = 2.0e4f * layer;
                    v_qs = 1.0e-5f * layer; v_qg = 5.0e-6f * layer;
                } else {
                    v_qr = 5.0e-6f * layer; v_nr = 2.0e4f * layer;
                    v_qi = 5.0e-5f * layer; v_ni = 5.0e4f * layer;
                    v_qs = 2.0e-5f * layer; v_qg = 5.0e-6f * layer;
                }
            } else {
                if (b == 0) { v_qr = 4.0e-5f * layer; v_nr = 1.0e5f * layer; }
                if (b == 1) { v_qs = 3.0e-5f * layer; }
                if (b == 2) { v_qg = 2.0e-5f * layer; }
                if (b == 3) { v_qi = 4.0e-5f * layer; v_ni = 4.0e4f * layer; }
            }
            qr.push_back(v_qr); qi.push_back(v_qi); qs.push_back(v_qs); qg.push_back(v_qg);
            nr.push_back(v_nr); ni.push_back(v_ni);
            bg.push_back(v_qg > 0.0f ? v_qg / 500.0f : 0.0f);
            rho.push_back(0.75f + 0.08f * static_cast<float>(b)
                                   + 0.03f * static_cast<float>(k));
            delz.push_back(8000.0f + 300.0f * static_cast<float>(k)
                                      + 100.0f * static_cast<float>(b));
            pii.push_back(1.0f);
            p.push_back(90000.0f - 4000.0f * static_cast<float>(k));
        }
    }

    State s;
    s.th = tensor2(B, K, th);       s.qv = tensor2(B, K, qv);
    s.qc = tensor2(B, K, qc);       s.qr = tensor2(B, K, qr);
    s.qi = tensor2(B, K, qi);       s.qs = tensor2(B, K, qs);
    s.qg = tensor2(B, K, qg);       s.nccn = tensor2(B, K, nccn);
    s.nc = tensor2(B, K, nc);       s.ni = tensor2(B, K, ni);
    s.nr = tensor2(B, K, nr);       s.bg = tensor2(B, K, bg);
    Forcing f;
    f.rho = tensor2(B, K, rho);     f.pii = tensor2(B, K, pii);
    f.p = tensor2(B, K, p);         f.delz = tensor2(B, K, delz);
    return Fixture{std::move(s), std::move(f), c10::nullopt, B, K, 20.0, 0.0, 0.0};
}

std::string hex32(float value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(8) << bits_from_f32(value);
    return out.str();
}

void emit_fixture_field(const char* name, const torch::Tensor& value, int64_t B, int64_t K) {
    auto t = value.detach().contiguous().cpu();
    if (t.scalar_type() != torch::kFloat32 || t.dim() != 2 ||
        t.size(0) != B || t.size(1) != K)
        throw std::runtime_error(std::string("fixture field shape/dtype mismatch: ") + name);
    const float* ptr = t.data_ptr<float>();
    for (int64_t b = 0; b < B; ++b)
        for (int64_t k = 0; k < K; ++k)
            std::cout << "KDM6FIX FIXIN " << name << " " << (b + 1) << " " << k
                      << " f32 " << hex32(ptr[b * K + k]) << "\n";
}

void emit_fixture_only(const Fixture& fixture) {
    namespace fx = g33_fixture_v1;
    std::cout << "KDM6FIX BEGIN v1 " << fx::FIXTURE_ID << " "
              << fixture.B << " " << fixture.K << "\n";
    static const char* names[12] = {
        "th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"};
    auto fields = fixture.state.fields();
    for (int i = 0; i < 12; ++i)
        emit_fixture_field(names[i], *fields[i], fixture.B, fixture.K);
    emit_fixture_field("rho", fixture.forcing.rho, fixture.B, fixture.K);
    emit_fixture_field("pii", fixture.forcing.pii, fixture.B, fixture.K);
    emit_fixture_field("p", fixture.forcing.p, fixture.B, fixture.K);
    emit_fixture_field("delz", fixture.forcing.delz, fixture.B, fixture.K);

    auto xl = fixture.xland.value().detach().contiguous().cpu();
    if (xl.scalar_type() != torch::kFloat32 || xl.dim() != 1 || xl.size(0) != fixture.B)
        throw std::runtime_error("fixture xland shape/dtype mismatch");
    const float* xp = xl.data_ptr<float>();
    for (int64_t b = 0; b < fixture.B; ++b)
        std::cout << "KDM6FIX FIXIN xland " << (b + 1) << " -1 f32 "
                  << hex32(xp[b]) << "\n";

    std::cout << "KDM6FIX PARAM dt f32 " << hex32(static_cast<float>(fixture.dt)) << "\n"
              << "KDM6FIX PARAM ncmin_land f32 "
              << hex32(static_cast<float>(fixture.ncmin_land)) << "\n"
              << "KDM6FIX PARAM ncmin_sea f32 "
              << hex32(static_cast<float>(fixture.ncmin_sea)) << "\n"
              << "KDM6FIX PARAM qmin f32 "
              << hex32(static_cast<float>(kdm6::constants::EPS)) << "\n"
              << "KDM6FIX END v1 " << fx::FIXTURE_ID << "\n";
}

void emit_tensor(const char* name, const torch::Tensor& value) {
    auto t = value.detach().contiguous().cpu();
    const auto dtype = t.scalar_type();
    if (dtype != torch::kFloat32 && dtype != torch::kFloat64)
        throw std::runtime_error(std::string("unsupported output dtype for ") + name);
    std::cout << "FIELD " << name << " " << (dtype == torch::kFloat32 ? "f32" : "f64")
              << " " << t.dim();
    for (int64_t d = 0; d < t.dim(); ++d) std::cout << " " << t.size(d);
    std::cout << " " << t.numel() << std::hex << std::setfill('0');
    if (dtype == torch::kFloat32) {
        const float* p = t.data_ptr<float>();
        for (int64_t i = 0; i < t.numel(); ++i) {
            uint32_t u; std::memcpy(&u, p + i, sizeof u);
            std::cout << " " << std::setw(8) << u;
        }
    } else {
        const double* p = t.data_ptr<double>();
        for (int64_t i = 0; i < t.numel(); ++i) {
            uint64_t u; std::memcpy(&u, p + i, sizeof u);
            std::cout << " " << std::setw(16) << u;
        }
    }
    std::cout << std::dec << std::setfill(' ') << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) {
        std::cerr << "usage: abc_driver legacy|conservative "
                     "closure3|species_iso|fourcase_v1 [--fixture-only]\n";
        return 2;
    }
    const std::string algorithm = argv[1];
    const std::string case_name = argv[2];
    const bool fixture_only = argc == 4 && std::string(argv[3]) == "--fixture-only";
    if (algorithm != "legacy" && algorithm != "conservative") {
        std::cerr << "algorithm must be legacy or conservative\n";
        return 2;
    }
    if (argc == 4 && !fixture_only) {
        std::cerr << "unknown fourth argument\n";
        return 2;
    }

    try {
        at::set_num_threads(1);
        try { at::set_num_interop_threads(1); } catch (...) {}
        torch::NoGradGuard no_grad;
        auto fixture = make_fixture(case_name);
        if (fixture_only) {
            if (case_name != "fourcase_v1")
                throw std::runtime_error("--fixture-only requires fourcase_v1");
            emit_fixture_only(fixture);
            return 0;
        }

        const auto variant = algorithm == "conservative"
            ? PhysicsVariant::ConservativeInterface : PhysicsVariant::Legacy;
        auto result = kdm6::kdm6_step(
            fixture.state, fixture.forcing, kdm6::make_parameters(0), fixture.dt,
            /*value_only=*/true, fixture.xland, fixture.ncmin_land, fixture.ncmin_sea,
            PhysicsOptions{variant});

        std::cout << "KDM6ABC 1 " << algorithm << " " << case_name << " "
                  << fixture.B << " " << fixture.K << "\n";
        static const char* names[12] = {
            "th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"};
        auto fields = result.state_out.fields();
        for (int i = 0; i < 12; ++i) emit_tensor(names[i], *fields[i]);
        emit_tensor("rain_increment", result.rain_increment);
        emit_tensor("snow_increment", result.snow_increment);
        emit_tensor("graupel_increment", result.graupel_increment);
        std::cout << "END\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ABC DRIVER FAIL: " << e.what() << "\n";
        return 1;
    }
}
