// C++ timestep-refinement leg: the SAME total 300 s reached in N kernel calls.
//
// Owner review §3 of the PR #100 review. The Fortran N=1 vs N=3 contrast was
// offered as a coefficient-only control and is not one: re-entering the kernel
// three times also re-runs entry normalisation three times, and the four external
// auxiliaries being stateless is not evidence that they are the complete set of
// call-local state.
//
// This driver supplies the control that separates those. The C++ port recomputes
// cpm/xl every subcycle, so at N=1 (one call, three internal subcycles) and N=3
// (three calls, one subcycle each) the coefficient refresh COUNT is identical --
// three either way. Any difference between them is therefore a call-boundary
// artifact with the thermodynamic policy held constant:
//
//   bitwise equal  -> the Fortran N=1/N=3 difference is attributable to the policy
//   different      -> external call segmentation is its own operator change, and
//                     the Fortran difference is a sum of at least two mechanisms
//
// A SEPARATE file from abc_driver.cpp, which it partly duplicates. That driver
// produces the four-leg decision bundles and the bundle manifest anchors its
// BINARY digest (`canonical_driver_sha256`); adding a mode to it would mean the
// source no longer reproduces the anchored artifact. The duplication is the cost
// of leaving the decision producer byte-identical.
//
// Emits the same G33R grammar as the Fortran refinement driver so one analyzer
// reads both -- but tags its algorithm `legacy-cpp` / `conservative-cpp`, so a
// mixed C++/Fortran set is rejected by the analyzer's algorithm check rather than
// silently compared. The k index here is HOST-K (bottom-first) as the C++ tensors
// carry it, NOT the Fortran driver's top-first convention: this leg is for
// C++-against-C++ comparison and a cross-backend read would need the flip the
// normalizer applies.
#include "kdm6/constants.h"
#include "kdm6/coordinator.h"
#include "kdm6/runtime.h"
#include "kdm6/state.h"

#ifdef KDM6_G33_FIXTURE_MULTISUBCYCLE
#include "g33_fixture_multisubcycle_v1.h"
#elif defined(KDM6_G33_FIXTURE_BOUNDARY_MAPPING)
#include "g33_fixture_boundary_mapping_v1.h"
#else
#include "g33_fixture_v1.h"
#endif

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

float f32_from_bits(std::uint32_t bits) {
    float v;
    std::memcpy(&v, &bits, sizeof v);
    return v;
}

std::uint32_t bits_from_f32(float v) {
    std::uint32_t u;
    std::memcpy(&u, &v, sizeof u);
    return u;
}

template <typename Arr>
std::vector<float> decode(const Arr& bits) {
    std::vector<float> out;
    out.reserve(std::size(bits));
    for (auto b : bits) out.push_back(f32_from_bits(b));
    return out;
}

torch::Tensor host2(int64_t B, int64_t K, const std::vector<float>& v) {
    return torch::from_blob(const_cast<float*>(v.data()), {B, K},
                            torch::kFloat32).clone();
}

torch::Tensor tensor1(const std::vector<float>& v) {
    return torch::from_blob(const_cast<float*>(v.data()),
                            {static_cast<int64_t>(v.size())},
                            torch::kFloat32).clone();
}

void emit(const char* name, const torch::Tensor& value, int64_t B, int64_t K) {
    auto t = value.detach().to(torch::kFloat32).contiguous().cpu().view({B, K});
    const float* p = t.data_ptr<float>();
    std::cout << std::hex << std::setfill('0');
    for (int64_t b = 0; b < B; ++b)
        for (int64_t k = 0; k < K; ++k)
            std::cout << "G33R STATE " << std::dec << name << " " << (b + 1) << " "
                      << k << " " << std::hex << std::setw(8)
                      << bits_from_f32(p[b * K + k]) << "\n";
    std::cout << std::dec << std::setfill(' ');
}

void emit_prec(int species, const torch::Tensor& value, int64_t B) {
    auto t = value.detach().to(torch::kFloat32).contiguous().cpu().view({B});
    const float* p = t.data_ptr<float>();
    for (int64_t b = 0; b < B; ++b)
        std::cout << "G33R PREC " << species << " " << (b + 1) << " " << std::hex
                  << std::setw(8) << std::setfill('0') << bits_from_f32(p[b])
                  << std::dec << std::setfill(' ') << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        torch::NoGradGuard no_grad;
        std::string algorithm = "legacy";
        int nsplit = 0;
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            if (a.rfind("--algo=", 0) == 0) {
                algorithm = a.substr(7);
                // Exact match or stop. Falling through to `legacy` would record a
                // run under an algorithm it was not executed with.
                if (algorithm != "legacy" && algorithm != "conservative")
                    throw std::runtime_error("--algo must be legacy or conservative");
            } else if (a.rfind("--nsplit=", 0) == 0) {
                nsplit = std::stoi(a.substr(9));
            } else {
                throw std::runtime_error("unknown argument: " + a);
            }
        }
        if (nsplit < 1) throw std::runtime_error("--nsplit=N (N >= 1) is required");

        namespace fx = g33_fixture_v1;
        State s;
        auto th = decode(fx::th_bits), qv = decode(fx::qv_bits),
             qc = decode(fx::qc_bits), qr = decode(fx::qr_bits),
             qi = decode(fx::qi_bits), qs = decode(fx::qs_bits),
             qg = decode(fx::qg_bits), nccn = decode(fx::nccn_bits),
             nc = decode(fx::nc_bits), ni = decode(fx::ni_bits),
             nr = decode(fx::nr_bits), bg = decode(fx::bg_bits);
        s.th = host2(fx::B, fx::K, th);     s.qv = host2(fx::B, fx::K, qv);
        s.qc = host2(fx::B, fx::K, qc);     s.qr = host2(fx::B, fx::K, qr);
        s.qi = host2(fx::B, fx::K, qi);     s.qs = host2(fx::B, fx::K, qs);
        s.qg = host2(fx::B, fx::K, qg);     s.nccn = host2(fx::B, fx::K, nccn);
        s.nc = host2(fx::B, fx::K, nc);     s.ni = host2(fx::B, fx::K, ni);
        s.nr = host2(fx::B, fx::K, nr);     s.bg = host2(fx::B, fx::K, bg);

        Forcing f;
        auto rho = decode(fx::rho_bits), pp = decode(fx::p_bits),
             pii = decode(fx::pii_bits), delz = decode(fx::delz_bits);
        f.rho = host2(fx::B, fx::K, rho);   f.p = host2(fx::B, fx::K, pp);
        f.pii = host2(fx::B, fx::K, pii);   f.delz = host2(fx::B, fx::K, delz);

        const float qmin = static_cast<float>(kdm6::constants::EPS);
        if (bits_from_f32(qmin) != fx::qmin_bits)
            throw std::runtime_error("shared fixture qmin differs from kdm6::constants::EPS");

        auto xland = tensor1(decode(fx::xland_bits));
        const double dt_total = f32_from_bits(fx::dt_bits);
        // Divided in f32 to match the Fortran leg exactly: 300/N is exact in f32
        // for every N in the sweep, but doing it in double and narrowing later
        // would be a different rounding on a member-by-member basis.
        const double delt = static_cast<double>(
            static_cast<float>(dt_total) / static_cast<float>(nsplit));
        const auto variant = algorithm == "conservative"
            ? PhysicsVariant::ConservativeInterface : PhysicsVariant::Legacy;

        torch::Tensor rain, snow, graupel;
        for (int n = 0; n < nsplit; ++n) {
            auto r = kdm6::kdm6_step(s, f, kdm6::make_parameters(0), delt,
                                     /*value_only=*/true, xland,
                                     f32_from_bits(fx::ncmin_land_bits),
                                     f32_from_bits(fx::ncmin_sea_bits),
                                     PhysicsOptions{variant});
            s = r.state_out;
            // The C++ returns per-step INCREMENTS while the Fortran accumulates
            // into rain/snow/graupel internally. Summing here is what makes the
            // two legs report the same quantity: the 300 s total, not the last
            // sub-call's share.
            rain = rain.defined() ? rain + r.rain_increment : r.rain_increment;
            snow = snow.defined() ? snow + r.snow_increment : r.snow_increment;
            graupel = graupel.defined() ? graupel + r.graupel_increment
                                        : r.graupel_increment;
        }

        // The loops/dtcld the KERNEL used, by its own rule (coordinator.cpp:1297,
        // runtime.cpp:415-420), not a hardcoded 1. At nsplit=1 this is 3 sub-cycles
        // of 100 s, which is precisely what makes the N=1/N=3 pair a control: the
        // C++ refreshes cpm/xl per SUB-CYCLE, so both arms refresh three times.
        // Printing 1 here would have described the control as the thing it is not.
        const int loops = kdm6::compute_loops_max(delt, kdm6::constants::DTCLDCR);
        const double dtcld = static_cast<double>(
            static_cast<float>(delt / static_cast<double>(loops)));
        std::cout << "G33R BEGIN nsplit " << nsplit << " rezero " << algorithm
                  << "-cpp delt " << std::fixed << std::setprecision(6) << delt
                  << " loops " << loops << " dtcld " << dtcld
                  << std::defaultfloat << "\n";
        static const char* names[12] = {"th", "qv", "qc", "qr", "qi", "qs", "qg",
                                        "nccn", "nc", "ni", "nr", "bg"};
        auto fields = s.fields();
        for (int i = 0; i < 12; ++i) emit(names[i], *fields[i], fx::B, fx::K);
        emit_prec(1, rain, fx::B);
        emit_prec(2, snow, fx::B);
        emit_prec(3, graupel, fx::B);
        std::cout << "G33R END\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "REFINE DRIVER FAIL: " << e.what() << "\n";
        return 1;
    }
}
