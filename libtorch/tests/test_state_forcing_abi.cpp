// Independent C ABI checks for joint 12-state + 4-forcing fp64 derivatives.
// This fixture is deliberately synthetic and smooth; the private 39-level host
// profile is validated by a separate local harness and is not committed here.

#include "kdm6_c_api.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <numeric>
#include <vector>

namespace {

constexpr int IM = 2;
constexpr int KM = 3;
constexpr int JM = 2;
constexpr std::size_t N = static_cast<std::size_t>(IM) * KM * JM;
constexpr std::size_t NS = 12 * N;
constexpr std::size_t NF = 4 * N;
constexpr uint32_t LEGACY = KDM6_PHYSICS_LEGACY;

// One packed field is a Fortran (im,kme,jme) column-major block; the twelve
// state and four forcing fields are then concatenated field-major.
std::size_t offset(int i, int k, int j) {
    return static_cast<std::size_t>(i) + IM * static_cast<std::size_t>(k) +
           IM * KM * static_cast<std::size_t>(j);
}

struct Inputs {
    std::vector<double> state = std::vector<double>(NS);
    std::vector<double> forcing = std::vector<double>(NF);

    Inputs() {
        for (int j = 0; j < JM; ++j) {
            for (int k = 0; k < KM; ++k) {
                for (int i = 0; i < IM; ++i) {
                    const auto n = offset(i, k, j);
                    auto s = [this, n](int field) -> double& { return state[static_cast<std::size_t>(field) * N + n]; };
                    auto f = [this, n](int field) -> double& { return forcing[static_cast<std::size_t>(field) * N + n]; };
                    const double z = static_cast<double>(k);
                    const double h = static_cast<double>(2 * i + 5 * j);
                    s(0) = 296.0 + 0.35 * z + 0.08 * h;       // TH [K]
                    s(1) = 0.010 + 0.0003 * z + 0.0001 * h;  // QV [kg/kg]
                    s(2) = 4.5e-4 + 1.0e-5 * z;              // QC
                    s(3) = 1.6e-4 + 5.0e-6 * h;              // QR
                    s(4) = 1.2e-4 + 4.0e-6 * z;              // QI
                    s(5) = 1.0e-4 + 3.0e-6 * h;              // QS
                    s(6) = 2.0e-5 + 1.0e-6 * z;              // QG
                    s(7) = 1.2e8 + 1.0e6 * h;                // NCCN, legacy raw basis
                    s(8) = 7.0e7 + 5.0e5 * z;                // NC
                    s(9) = 2.0e6 + 1.0e4 * h;                // NI
                    s(10) = 1.5e6 + 1.0e4 * z;               // NR
                    s(11) = 2.0e-8 + 1.0e-9 * h;             // BG [m^3/kg]

                    const double p = 90000.0 - 8500.0 * z - 250.0 * h;
                    f(0) = 1.03 - 0.025 * z + 0.002 * h;   // DEN [kg/m^3]
                    f(1) = std::pow(p / 100000.0, 0.2854);  // PII [1]
                    f(2) = p;                               // P [Pa]
                    f(3) = 240.0 + 35.0 * z + 3.0 * h;    // DELZ [m]
                }
            }
        }
    }
};

void require_ok(int rc, const char* what) {
    if (rc != KDM6_OK) {
        std::cerr << what << " returned C ABI error " << rc << '\n';
        std::abort();
    }
}

std::vector<double> value_forward(const Inputs& x, bool joint, int64_t dry_number = 0) {
    std::vector<double> y(NS, -999.0);
    kdm6_handle_t* h = reinterpret_cast<kdm6_handle_t*>(static_cast<uintptr_t>(1));
    const int rc = joint
        ? kdm6_step_ad_state_forcing_c(x.state.data(), x.forcing.data(), IM, KM, JM,
              20.0, 1, y.data(), &h, nullptr, 100.0, 10.0, LEGACY, dry_number)
        : (dry_number == 0
            ? kdm6_step_ad_c(x.state.data(), x.forcing.data(), IM, KM, JM,
                  20.0, 1, y.data(), &h, nullptr, 100.0, 10.0)
            : kdm6_step_ad_number_c(x.state.data(), x.forcing.data(), IM, KM, JM,
                  20.0, 1, y.data(), &h, nullptr, 100.0, 10.0, LEGACY, dry_number));
    require_ok(rc, "value-only forward");
    assert(h == nullptr);
    return y;
}

struct DerivativeHandle {
    kdm6_handle_t* value = nullptr;
    DerivativeHandle() = default;
    DerivativeHandle(const DerivativeHandle&) = delete;
    DerivativeHandle& operator=(const DerivativeHandle&) = delete;
    DerivativeHandle(DerivativeHandle&& other) noexcept : value(other.value) {
        other.value = nullptr;
    }
    DerivativeHandle& operator=(DerivativeHandle&& other) noexcept {
        if (this != &other) {
            if (value) kdm6_handle_closep_c(&value);
            value = other.value;
            other.value = nullptr;
        }
        return *this;
    }
    ~DerivativeHandle() { if (value) kdm6_handle_closep_c(&value); }
};

DerivativeHandle joint_handle(const Inputs& x, std::vector<double>& y, int64_t dry_number = 0) {
    DerivativeHandle h;
    require_ok(kdm6_step_ad_state_forcing_c(
        x.state.data(), x.forcing.data(), IM, KM, JM, 20.0, 0, y.data(),
        &h.value, nullptr, 100.0, 10.0, LEGACY, dry_number), "joint derivative forward");
    assert(h.value != nullptr);
    return h;
}

std::vector<double> scaled_direction(std::size_t size, std::size_t block_count,
                                     const std::vector<double>& base, int first_field,
                                     const std::vector<double>& scales) {
    std::vector<double> v(size, 0.0);
    for (int field = 0; field < first_field + static_cast<int>(block_count); ++field) {
        const double scale = scales[static_cast<std::size_t>(field - first_field)];
        for (std::size_t n = 0; n < N; ++n) {
            const double phase = 0.37 * static_cast<double>(1 + n + 3 * field);
            v[static_cast<std::size_t>(field - first_field) * N + n] =
                scale * (0.6 * std::sin(phase) + 0.4 * std::cos(0.71 * phase));
        }
    }
    (void)base;
    return v;
}

std::vector<double> combine_direction(const std::vector<double>& vs,
                                      const std::vector<double>& vf) {
    std::vector<double> v;
    v.reserve(vs.size() + vf.size());
    v.insert(v.end(), vs.begin(), vs.end());
    v.insert(v.end(), vf.begin(), vf.end());
    return v;
}

double dot(const std::vector<double>& a, const std::vector<double>& b) {
    assert(a.size() == b.size());
    double result = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) result += a[i] * b[i];
    return result;
}

double norm(const std::vector<double>& a) { return std::sqrt(dot(a, a)); }

std::vector<double> fd_direction(const Inputs& x, const std::vector<double>& vs,
                                 const std::vector<double>& vf, double eps,
                                 int64_t dry_number = 0) {
    Inputs plus = x, minus = x;
    for (std::size_t n = 0; n < NS; ++n) {
        plus.state[n] += eps * vs[n];
        minus.state[n] -= eps * vs[n];
    }
    for (std::size_t n = 0; n < NF; ++n) {
        plus.forcing[n] += eps * vf[n];
        minus.forcing[n] -= eps * vf[n];
    }
    const auto yp = value_forward(plus, true, dry_number);
    const auto ym = value_forward(minus, true, dry_number);
    std::vector<double> fd(NS);
    for (std::size_t n = 0; n < NS; ++n) fd[n] = (yp[n] - ym[n]) / (2.0 * eps);
    return fd;
}

void check_fd_sweep(const Inputs& x, const std::vector<double>& vs,
                    const std::vector<double>& vf, const std::vector<double>& jv,
                    const char* label, int64_t dry_number = 0) {
    const std::array<double, 4> epsilons{2.0e-2, 6.0e-3, 1.8e-3, 5.4e-4};
    const std::array<double, 12> output_scales{
        1.0, 1.0e-2, 1.0e-3, 1.0e-3, 1.0e-3, 1.0e-3,
        1.0e-3, 1.0e8, 1.0e8, 1.0e6, 1.0e6, 1.0e-7};
    std::array<double, 12> best_normalized_error{};
    best_normalized_error.fill(std::numeric_limits<double>::infinity());
    for (double eps : epsilons) {
        const auto fd = fd_direction(x, vs, vf, eps, dry_number);
        for (std::size_t field = 0; field < output_scales.size(); ++field) {
            double error2 = 0.0;
            for (std::size_t n = 0; n < N; ++n) {
                const std::size_t idx = field * N + n;
                const double error = (fd[idx] - jv[idx]) / output_scales[field];
                error2 += error * error;
            }
            best_normalized_error[field] = std::min(best_normalized_error[field], std::sqrt(error2));
        }
    }
    for (std::size_t field = 0; field < output_scales.size(); ++field) {
        double jv2 = 0.0;
        for (std::size_t n = 0; n < N; ++n) {
            const double scaled = jv[field * N + n] / output_scales[field];
            jv2 += scaled * scaled;
        }
        const double normalized_jvp = std::sqrt(jv2);
        // Per-output physical scales keep large number blocks from masking a
        // bad temperature/moisture/forcing derivative in one concatenated norm.
        const double tolerance = 2.0e-7 + 2.0e-3 * normalized_jvp;
        if (!(best_normalized_error[field] < tolerance)) {
            std::cerr << label << " finite-difference field=" << field
                      << " normalized_error=" << best_normalized_error[field]
                      << " normalized_jvp=" << normalized_jvp
                      << " limit=" << tolerance << '\n';
            std::abort();
        }
    }
}

void test_joint_forward_is_additive_and_legacy_value_stays_bitwise() {
    Inputs x;
    const auto old = value_forward(x, false);
    const auto joint = value_forward(x, true, 0);
    assert(old.size() == joint.size());
    assert(std::memcmp(old.data(), joint.data(), old.size() * sizeof(double)) == 0);

    // A selector error fails before graph work and leaves the caller's output
    // canary intact while clearing the output handle.
    std::vector<double> out(NS, 9876.5);
    kdm6_handle_t* handle = reinterpret_cast<kdm6_handle_t*>(static_cast<uintptr_t>(1));
    const int rc = kdm6_step_ad_state_forcing_c(
        x.state.data(), x.forcing.data(), IM, KM, JM, 20.0, 1, out.data(), &handle,
        nullptr, 100.0, 10.0, UINT32_MAX, 0);
    assert(rc == KDM6_ERR_INVALID_ARG);
    assert(handle == nullptr);
    assert(std::all_of(out.begin(), out.end(), [](double v) { return v == 9876.5; }));

    std::fill(out.begin(), out.end(), 4321.0);
    handle = reinterpret_cast<kdm6_handle_t*>(static_cast<uintptr_t>(1));
    const int bad_number = kdm6_step_ad_state_forcing_c(
        x.state.data(), x.forcing.data(), IM, KM, JM, 20.0, 1, out.data(), &handle,
        nullptr, 100.0, 10.0, LEGACY, -1);
    assert(bad_number == KDM6_ERR_INVALID_ARG);
    assert(handle == nullptr);
    assert(std::all_of(out.begin(), out.end(), [](double v) { return v == 4321.0; }));
}

void test_joint_jvp_vjp_dot_and_independent_directional_differences() {
    Inputs x;
    std::vector<double> y(NS);
    auto h = joint_handle(x, y);

    const std::vector<double> state_scales{
        2.0e-1, 2.0e-4, 2.0e-5, 2.0e-5, 2.0e-5, 2.0e-5,
        2.0e-5, 2.0e5, 2.0e5, 2.0e4, 2.0e4, 2.0e-9};
    const std::vector<double> forcing_scales{2.0e-2, 2.0e-4, 2.0e2, 2.0};
    const auto vs = scaled_direction(NS, 12, x.state, 0, state_scales);
    const auto vf = scaled_direction(NF, 4, x.forcing, 0, forcing_scales);
    std::vector<double> u(NS);
    for (std::size_t n = 0; n < NS; ++n) {
        u[n] = std::sin(0.23 * static_cast<double>(n + 1)) +
               0.3 * std::cos(0.11 * static_cast<double>(n + 3));
    }

    std::vector<double> jv_state(NS, 0.0), jv_force(NS, 0.0), jv_mixed(NS, 0.0);
    const std::vector<double> zero_state(NS, 0.0), zero_force(NF, 0.0);
    require_ok(kdm6_handle_state_forcing_jvp_c(h.value, vs.data(), zero_force.data(),
              jv_state.data()), "state-only JVP");
    require_ok(kdm6_handle_state_forcing_jvp_c(h.value, zero_state.data(), vf.data(),
              jv_force.data()), "forcing-only JVP");
    require_ok(kdm6_handle_state_forcing_jvp_c(h.value, vs.data(), vf.data(),
              jv_mixed.data()), "mixed JVP");

    check_fd_sweep(x, vs, zero_force, jv_state, "state-only");
    check_fd_sweep(x, zero_state, vf, jv_force, "forcing-only");
    check_fd_sweep(x, vs, vf, jv_mixed, "mixed");

    // Probe each forcing leaf independently so a missing rho/pii/p/delz path
    // cannot hide behind cancellation in the combined forcing direction.
    const std::array<double, 4> force_scales{2.0e-2, 2.0e-4, 2.0e2, 2.0};
    for (std::size_t forcing_field = 0; forcing_field < force_scales.size(); ++forcing_field) {
        std::vector<double> one_force(NF, 0.0), one_jvp(NS, 0.0);
        for (std::size_t n = 0; n < N; ++n) {
            const double phase = 0.29 * static_cast<double>(1 + n + forcing_field);
            one_force[forcing_field * N + n] =
                force_scales[forcing_field] * (0.7 * std::sin(phase) + 0.2 * std::cos(0.53 * phase));
        }
        require_ok(kdm6_handle_state_forcing_jvp_c(h.value, zero_state.data(), one_force.data(),
                  one_jvp.data()), "single-forcing JVP");
        if (!(norm(one_jvp) > 0.0)) {
            std::cerr << "forcing field " << forcing_field << " has zero JVP in smooth fixture\n";
            std::abort();
        }
        check_fd_sweep(x, zero_state, one_force, one_jvp, "single-forcing");
    }

    std::vector<double> gs(NS, -777.0), gf(NF, -888.0);
    require_ok(kdm6_handle_state_forcing_vjp_c(h.value, u.data(), gs.data(), gf.data()),
              "joint VJP");
    const auto v = combine_direction(vs, vf);
    const auto g = combine_direction(gs, gf);
    const double lhs = dot(jv_mixed, u);
    const double rhs = dot(v, g);
    const double adjoint_error = std::abs(lhs - rhs) / std::max({1.0, std::abs(lhs), std::abs(rhs)});
    assert(adjoint_error < 2.0e-10);

    assert(std::all_of(jv_mixed.begin(), jv_mixed.end(), [](double v0) { return std::isfinite(v0); }));
    assert(std::all_of(gs.begin(), gs.end(), [](double v0) { return std::isfinite(v0); }));
    assert(std::all_of(gf.begin(), gf.end(), [](double v0) { return std::isfinite(v0); }));
    assert(norm(jv_state) > 0.0 && norm(jv_force) > 0.0 && norm(jv_mixed) > 0.0);
    assert(norm(gf) > 0.0);
}

void test_new_joint_operations_reject_old_state_only_handles_without_writes() {
    Inputs x;
    std::vector<double> y(NS);
    kdm6_handle_t* old = nullptr;
    require_ok(kdm6_step_ad_c(x.state.data(), x.forcing.data(), IM, KM, JM, 20.0,
              0, y.data(), &old, nullptr, 100.0, 10.0), "old state-only AD forward");
    assert(old != nullptr);
    std::vector<double> u(NS, 1.0), gs(NS, 123.0), gf(NF, 456.0);
    std::vector<double> vs(NS, 1.0), vf(NF, 1.0), out(NS, 789.0);
    assert(kdm6_handle_state_forcing_vjp_c(old, u.data(), gs.data(), gf.data()) == KDM6_ERR_INVALID_ARG);
    assert(kdm6_handle_state_forcing_jvp_c(old, vs.data(), vf.data(), out.data()) == KDM6_ERR_INVALID_ARG);
    assert(std::all_of(gs.begin(), gs.end(), [](double v) { return v == 123.0; }));
    assert(std::all_of(gf.begin(), gf.end(), [](double v) { return v == 456.0; }));
    assert(std::all_of(out.begin(), out.end(), [](double v) { return v == 789.0; }));
    std::vector<double> state_grad(NS, 11.0);
    assert(kdm6_handle_vjp_c(old, u.data(), state_grad.data()) == KDM6_OK);
    assert(std::any_of(state_grad.begin(), state_grad.end(), [](double v) { return v != 11.0; }));
    kdm6_handle_closep_c(&old);
    assert(old == nullptr);
}

void test_dry_number_qv_density_conversion_is_inside_joint_ad_graph() {
    // Here all four QN inputs intentionally use a homogeneous #/kg-dry basis;
    // this is a synthetic unit-contract fixture, not the captured host NN
    // profile (which is a special #/m^3 CCN field on its first physics step).
    Inputs x;
    const auto legacy_number = value_forward(x, false, 1);
    const auto joint_number = value_forward(x, true, 1);
    assert(std::memcmp(legacy_number.data(), joint_number.data(),
                       legacy_number.size() * sizeof(double)) == 0);

    std::vector<double> y(NS);
    auto h = joint_handle(x, y, 1);
    std::vector<double> vs(NS, 0.0), vf(NF, 0.0), tangent(NS, 0.0);
    // Isolate the dry density conversion: n_volume = n_dry * rho/(1+qv).
    for (std::size_t n = 0; n < N; ++n) {
        vs[N + n] = 2.0e-4 * (1.0 + 0.1 * static_cast<double>(n));
        vf[n] = 2.0e-2 * (1.0 - 0.05 * static_cast<double>(n));
    }
    require_ok(kdm6_handle_state_forcing_jvp_c(h.value, vs.data(), vf.data(), tangent.data()),
              "dry-number mixed JVP");
    check_fd_sweep(x, vs, vf, tangent, "dry-number qv/rho mixed", 1);

    std::vector<double> u(NS, 0.0), gs(NS, 0.0), gf(NF, 0.0);
    for (std::size_t n = 0; n < NS; ++n) u[n] = std::cos(0.17 * static_cast<double>(n + 1));
    require_ok(kdm6_handle_state_forcing_vjp_c(h.value, u.data(), gs.data(), gf.data()),
              "dry-number joint VJP");
    const auto v = combine_direction(vs, vf);
    const auto g = combine_direction(gs, gf);
    const double lhs = dot(tangent, u);
    const double rhs = dot(v, g);
    assert(std::abs(lhs - rhs) / std::max({1.0, std::abs(lhs), std::abs(rhs)}) < 2.0e-10);
}

}  // namespace

int main() {
    std::cout << "test_state_forcing_abi: smooth synthetic C ABI contract\n";
    test_joint_forward_is_additive_and_legacy_value_stays_bitwise();
    test_joint_jvp_vjp_dot_and_independent_directional_differences();
    test_new_joint_operations_reject_old_state_only_handles_without_writes();
    test_dry_number_qv_density_conversion_is_inside_joint_ad_graph();
    std::cout << "PASS test_state_forcing_abi\n";
    return 0;
}
