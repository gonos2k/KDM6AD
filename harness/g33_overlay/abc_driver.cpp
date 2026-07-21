// C++ A/B/C non-invasiveness driver for the G3.3-M diagnostic overlay.
//
// One executable is linked against the canonical archive (A); a second is linked
// with all four diagnostic overlay objects replacing their canonical archive
// members (B/C).  The diagnostic executable is run twice: with every G33 env
// variable absent (B), then with the sealed dump environment active (C).
//
// Output is a strict raw-bit text protocol.  The Python gate validates the field
// set/dtypes/shapes before comparing the complete A/B/C byte streams, so an empty
// or truncated output cannot pass merely because all three runs failed alike.

#include "kdm6/runtime.h"
#include "kdm6/state.h"

#include <torch/torch.h>

#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using kdm6::Forcing;
using kdm6::PhysicsOptions;
using kdm6::PhysicsVariant;
using kdm6::State;

struct Fixture {
    State state;
    Forcing forcing;
    int64_t B;
    int64_t K;
    double dt;
};

torch::Tensor tensor2(int64_t B, int64_t K, const std::vector<float>& values) {
    if (static_cast<int64_t>(values.size()) != B * K)
        throw std::runtime_error("fixture tensor has the wrong element count");
    return torch::tensor(values, torch::TensorOptions().dtype(torch::kFloat32))
        .reshape({B, K});
}

Fixture make_fixture(const std::string& name) {
    const int64_t K = 4;
    const int64_t B = name == "closure3" ? 3 : 4;
    if (name != "closure3" && name != "species_iso")
        throw std::runtime_error("case must be closure3 or species_iso");

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

            // Large positive layers deliberately keep every initial normalized
            // fall CFL below one, making the sealed one-substep schedule explicit
            // rather than inferred from the producer.
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
    return Fixture{std::move(s), std::move(f), B, K, 20.0};
}

void emit_tensor(const char* name, const torch::Tensor& value) {
    auto t = value.detach().contiguous().cpu();
    const auto dtype = t.scalar_type();
    if (dtype != torch::kFloat32 && dtype != torch::kFloat64)
        throw std::runtime_error(std::string("unsupported output dtype for ") + name);

    std::cout << "FIELD " << name << " "
              << (dtype == torch::kFloat32 ? "f32" : "f64")
              << " " << t.dim();
    for (int64_t d = 0; d < t.dim(); ++d) std::cout << " " << t.size(d);
    std::cout << " " << t.numel();

    std::cout << std::hex << std::setfill('0');
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
    if (argc != 3) {
        std::cerr << "usage: abc_driver legacy|conservative closure3|species_iso\n";
        return 2;
    }
    const std::string algorithm = argv[1];
    const std::string case_name = argv[2];
    if (algorithm != "legacy" && algorithm != "conservative") {
        std::cerr << "algorithm must be legacy or conservative\n";
        return 2;
    }

    try {
        at::set_num_threads(1);
        try { at::set_num_interop_threads(1); } catch (...) {}
        torch::NoGradGuard no_grad;
        auto fixture = make_fixture(case_name);
        const auto variant = algorithm == "conservative"
            ? PhysicsVariant::ConservativeInterface : PhysicsVariant::Legacy;
        auto result = kdm6::kdm6_step(
            fixture.state, fixture.forcing, kdm6::make_parameters(0), fixture.dt,
            /*value_only=*/true, c10::nullopt, 0.0, 0.0, PhysicsOptions{variant});

        std::cout << "KDM6ABC 1 " << algorithm << " " << case_name << " "
                  << fixture.B << " " << fixture.K << "\n";
        static const char* names[12] = {
            "th", "qv", "qc", "qr", "qi", "qs", "qg",
            "nccn", "nc", "ni", "nr", "bg"
        };
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
