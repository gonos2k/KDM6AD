#include "kdm6/runtime.h"

#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include <unistd.h>

namespace {
constexpr std::array<char, 8> kInputMagic{{'K', '6', 'B', 'U', 'D', 'G', '1', '\0'}};
constexpr std::array<char, 8> kOutputMagic{{'K', '6', 'B', 'O', 'U', 'T', '1', '\0'}};
constexpr std::uint32_t kLevels = 2;

template <typename T>
void write_value(std::ofstream& out, const T& value) {
    out.write(reinterpret_cast<const char*>(&value), sizeof(value));
    assert(out.good());
}

template <typename T>
T read_value(std::ifstream& in) {
    T value{};
    in.read(reinterpret_cast<char*>(&value), sizeof(value));
    assert(in.good());
    return value;
}

std::string shell_quote(const std::string& text) {
    std::string quoted = "'";
    for (char c : text) {
        if (c == '\'') quoted += "'\\''";
        else quoted += c;
    }
    quoted += "'";
    return quoted;
}

void compare_tensor_bytes(const torch::Tensor& tensor, const double* expected,
                          std::size_t count) {
    auto flat = tensor.contiguous().view({-1});
    assert(flat.scalar_type() == torch::kFloat64);
    assert(flat.numel() == static_cast<std::int64_t>(count));
    assert(std::memcmp(flat.data_ptr<double>(), expected, count * sizeof(double)) == 0);
}
}  // namespace

int main(int argc, char** argv) {
    assert(argc == 2);
    const std::filesystem::path tool = argv[1];
    const auto work = std::filesystem::temp_directory_path() /
        ("kdm6-column-budget-test-" + std::to_string(::getpid()));
    std::filesystem::remove_all(work);
    std::filesystem::create_directories(work);
    const auto input = work / "request.bin";
    const auto output = work / "result.bin";

    // A small finite native-coordinate fixture. The test compares the CLI
    // result against a direct call on the exact same packed binary64 operands.
    const std::array<std::array<double, kLevels>, 12> s{{
        {{270.0, 268.0}}, {{0.004, 0.003}}, {{1.0e-4, 8.0e-5}},
        {{1.0e-5, 2.0e-5}}, {{1.0e-5, 1.2e-5}}, {{1.0e-5, 1.1e-5}},
        {{1.0e-5, 9.0e-6}}, {{1.0e8, 1.0e8}}, {{1.0e5, 1.2e5}},
        {{1.0e4, 1.1e4}}, {{1.0e4, 1.1e4}}, {{1.0e-7, 1.0e-7}},
    }};
    const std::array<std::array<double, kLevels>, 4> f{{
        {{1.0, 0.8}}, {{0.85, 0.82}}, {{70000.0, 60000.0}}, {{1000.0, 1200.0}},
    }};
    constexpr double dt = 20.0;
    constexpr double xland_value = 2.0;
    constexpr double ncmin_land = 8.0e4;
    constexpr double ncmin_sea = 5.0e4;
    {
        std::ofstream out(input, std::ios::binary);
        out.write(kInputMagic.data(), kInputMagic.size());
        write_value(out, std::uint32_t{1});
        write_value(out, kLevels);
        write_value(out, dt);
        write_value(out, xland_value);
        write_value(out, ncmin_land);
        write_value(out, ncmin_sea);
        for (const auto& field : s) for (double v : field) write_value(out, v);
        for (const auto& field : f) for (double v : field) write_value(out, v);
    }

    const std::string command = shell_quote(tool.string()) + " --input " + shell_quote(input.string()) +
                                " --output " + shell_quote(output.string());
    assert(std::system(command.c_str()) == 0);
    assert(std::filesystem::is_regular_file(output));

    auto options = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
    kdm6::State state;
    auto sf = state.fields();
    for (std::size_t n = 0; n < sf.size(); ++n) {
        *sf[n] = torch::from_blob(const_cast<double*>(s[n].data()), {1, kLevels}, options).clone();
    }
    kdm6::Forcing forcing;
    auto ff = forcing.fields();
    for (std::size_t n = 0; n < ff.size(); ++n) {
        *ff[n] = torch::from_blob(const_cast<double*>(f[n].data()), {1, kLevels}, options).clone();
    }
    auto xland = torch::full({1}, xland_value, options);
    auto params = kdm6::make_parameters(0, torch::kCPU, torch::kFloat64);
    kdm6::FnResult expected;
    {
        torch::NoGradGuard no_grad;
        expected = kdm6::kdm6_fn(state, forcing, params, dt, xland,
                                 ncmin_land, ncmin_sea, kdm6::PhysicsOptions{}, false);
    }

    std::ifstream in(output, std::ios::binary);
    std::array<char, 8> magic{};
    in.read(magic.data(), magic.size());
    assert(in.good() && magic == kOutputMagic);
    assert(read_value<std::uint32_t>(in) == 1);
    assert(read_value<std::uint32_t>(in) == kLevels);
    for (const auto& field : s) {
        for (double expected_value : field) {
            const double actual = read_value<double>(in);
            assert(std::memcmp(&actual, &expected_value, sizeof(double)) == 0);
        }
    }
    for (const auto& field : f) {
        for (double expected_value : field) {
            const double actual = read_value<double>(in);
            assert(std::memcmp(&actual, &expected_value, sizeof(double)) == 0);
        }
    }
    const auto expected_state_fields = expected.state_out.fields();
    for (const auto* field : expected_state_fields) {
        auto flat = field->contiguous().view({-1});
        assert(flat.numel() == kLevels);
        const auto* values = flat.data_ptr<double>();
        for (std::uint32_t k = 0; k < kLevels; ++k) {
            const double actual = read_value<double>(in);
            assert(std::memcmp(&actual, values + k, sizeof(double)) == 0);
        }
    }
    const std::array<torch::Tensor, 3> precip{{
        expected.rain_increment, expected.snow_increment, expected.graupel_increment}};
    for (const auto& field : precip) {
        const double expected_value = field.contiguous().view({-1}).item<double>();
        const double actual = read_value<double>(in);
        assert(std::memcmp(&actual, &expected_value, sizeof(double)) == 0);
    }
    assert(in.peek() == std::ifstream::traits_type::eof());
    std::filesystem::remove_all(work);
    return 0;
}
