// Independent value-only reference for the native-f32 ABI precision gate.
//
// This program is a direct C++ runtime call, not a C ABI entry and not a WRF
// host step. It reads the existing K6BATI1 request, applies the exact host
// float32 storage/widening boundary to state and forcing, and writes the
// full-f64 state/precip/rhog result. Run it only after the root-approved test
// budget. Link it against the same pinned actual-QR archive as the test DSO.

#include "kdm6/runtime.h"

#include <array>
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

constexpr std::array<char, 8> kRequestMagic{{'K','6','B','A','T','I','1','\0'}};
constexpr std::array<char, 8> kReferenceMagic{{'K','6','R','E','F','1','\0','\0'}};
constexpr std::uint32_t kVersion = 1;
constexpr std::uint32_t kStateFields = 12;
constexpr std::uint32_t kForcingFields = 4;
constexpr std::uint64_t kMaxBatch = 4096;
constexpr std::uint64_t kMaxLevels = 256;
constexpr std::size_t kRequestHeader = 8 + 3 * sizeof(std::uint32_t) + 3 * sizeof(double);

static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
              "reference protocol requires IEEE binary64");

[[noreturn]] void fail(const std::string& message) { throw std::runtime_error(message); }

bool little_endian() {
    const std::uint16_t one = 1;
    return *reinterpret_cast<const unsigned char*>(&one) == 1;
}

std::uint64_t read_fpcr() {
#if defined(__aarch64__)
    std::uint64_t value = 0;
    asm volatile("mrs %0, fpcr" : "=r"(value));
    return value;
#else
    return std::numeric_limits<std::uint64_t>::max();
#endif
}

void read_exact(std::ifstream& in, char* data, std::size_t size, const char* what) {
    in.read(data, static_cast<std::streamsize>(size));
    if (in.gcount() != static_cast<std::streamsize>(size)) fail(std::string("truncated ") + what);
}

void write_exact(int fd, const void* data, std::size_t size) {
    const auto* bytes = static_cast<const unsigned char*>(data);
    std::size_t done = 0;
    while (done < size) {
        const ssize_t n = ::write(fd, bytes + done, size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) fail("reference write failed");
        done += static_cast<std::size_t>(n);
    }
}

void write_u32(int fd, std::uint32_t value) { write_exact(fd, &value, sizeof(value)); }
void write_double(int fd, double value) { write_exact(fd, &value, sizeof(value)); }

std::vector<double> tensor_values(const torch::Tensor& value, std::int64_t expected,
                                  const char* name) {
    auto flat = value.contiguous().view({-1});
    if (flat.numel() != expected || flat.scalar_type() != torch::kFloat64)
        fail(std::string("runtime output shape/dtype differs: ") + name);
    std::vector<double> values(static_cast<std::size_t>(expected));
    std::memcpy(values.data(), flat.data_ptr<double>(), values.size() * sizeof(double));
    for (double item : values) if (!std::isfinite(item)) fail(std::string("nonfinite output: ") + name);
    return values;
}

void run(const std::filesystem::path& request_path,
         const std::filesystem::path& output_path,
         const std::string& request_sha256) {
    if (!little_endian()) fail("native reference runner requires little endian");
    if (request_sha256.size() != 64) fail("request SHA-256 must be 64 hex characters");
    std::ifstream in(request_path, std::ios::binary);
    if (!in) fail("cannot open request");
    std::array<char, kRequestHeader> header{};
    read_exact(in, header.data(), header.size(), "request header");
    if (std::memcmp(header.data(), kRequestMagic.data(), kRequestMagic.size()) != 0)
        fail("request magic differs from K6BATI1");
    std::uint32_t version = 0, batch32 = 0, levels32 = 0;
    std::memcpy(&version, header.data() + 8, sizeof(version));
    std::memcpy(&batch32, header.data() + 12, sizeof(batch32));
    std::memcpy(&levels32, header.data() + 16, sizeof(levels32));
    if (version != kVersion || batch32 == 0 || batch32 > kMaxBatch || levels32 == 0 || levels32 > kMaxLevels)
        fail("unsupported request version or dimensions");
    const auto batch = static_cast<std::int64_t>(batch32);
    const auto levels = static_cast<std::int64_t>(levels32);
    double dt = 0.0, ncmin_land = 0.0, ncmin_sea = 0.0;
    std::memcpy(&dt, header.data() + 20, sizeof(double));
    std::memcpy(&ncmin_land, header.data() + 28, sizeof(double));
    std::memcpy(&ncmin_sea, header.data() + 36, sizeof(double));
    if (!std::isfinite(dt) || dt <= 0.0 || !std::isfinite(ncmin_land) || ncmin_land < 0.0 ||
        !std::isfinite(ncmin_sea) || ncmin_sea < 0.0) fail("invalid request scalars");
    const std::size_t state_count = static_cast<std::size_t>(kStateFields * batch * levels);
    const std::size_t forcing_count = static_cast<std::size_t>(kForcingFields * batch * levels);
    const std::size_t xland_count = static_cast<std::size_t>(batch);
    std::vector<double> state(state_count), forcing(forcing_count), xland_wide(xland_count);
    read_exact(in, reinterpret_cast<char*>(state.data()), state.size() * sizeof(double), "state");
    read_exact(in, reinterpret_cast<char*>(forcing.data()), forcing.size() * sizeof(double), "forcing");
    read_exact(in, reinterpret_cast<char*>(xland_wide.data()), xland_wide.size() * sizeof(double), "xland");
    char extra = 0;
    if (in.get(extra)) fail("request has trailing bytes");

    // The operational ABI first narrows each input to REAL4. The candidate
    // reference must start from precisely those values, not original request f64.
    auto widen_host_f32 = [](std::vector<double>& values, const char* name) {
        for (double& item : values) {
            if (!std::isfinite(item)) fail(std::string("nonfinite input: ") + name);
            const float narrow = static_cast<float>(item);
            if (!std::isfinite(narrow)) fail(std::string("float32 input overflow: ") + name);
            item = static_cast<double>(narrow);
        }
    };
    widen_host_f32(state, "state");
    widen_host_f32(forcing, "forcing");
    std::vector<float> xland(xland_count);
    for (std::size_t i = 0; i < xland_count; ++i) {
        const float narrow = static_cast<float>(xland_wide[i]);
        if (narrow != 1.0f && narrow != 2.0f) fail("invalid native XLAND");
        xland[i] = narrow;
        xland_wide[i] = static_cast<double>(narrow);
    }
    for (std::size_t b = 0; b < xland_count; ++b) {
        for (std::size_t k = 0; k < static_cast<std::size_t>(levels); ++k) {
            const std::size_t n = b * static_cast<std::size_t>(levels) + k;
            for (std::size_t f = 0; f < kForcingFields; ++f)
                if (!(forcing[f * xland_count * static_cast<std::size_t>(levels) + n] > 0.0))
                    fail("nonpositive native forcing");
        }
    }

    const auto options64 = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
    auto field64 = [&](const std::vector<double>& values, std::size_t offset) {
        return torch::from_blob(const_cast<double*>(values.data() + offset), {batch, levels}, options64).clone();
    };
    kdm6::State state_in;
    auto state_fields = state_in.fields();
    for (std::size_t field = 0; field < state_fields.size(); ++field)
        *state_fields[field] = field64(state, field * static_cast<std::size_t>(batch * levels));
    kdm6::Forcing forcing_in;
    auto forcing_fields = forcing_in.fields();
    for (std::size_t field = 0; field < forcing_fields.size(); ++field)
        *forcing_fields[field] = field64(forcing, field * static_cast<std::size_t>(batch * levels));
    auto xland_tensor = torch::from_blob(xland.data(), {batch}, torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU)).clone();
    auto params = kdm6::make_parameters(0, torch::kCPU, torch::kFloat64);
    const std::uint64_t fpcr_before = read_fpcr();
    const std::int32_t rounding_before = std::fegetround();
    kdm6::FnResult result;
    {
        torch::NoGradGuard guard;
        result = kdm6::kdm6_fn(state_in, forcing_in, params, dt, xland_tensor,
                               ncmin_land, ncmin_sea, kdm6::PhysicsOptions{}, false);
    }
    const std::uint64_t fpcr_after = read_fpcr();
    const std::int32_t rounding_after = std::fegetround();
    auto echoed_state_fields = state_in.fields();
    auto echoed_forcing_fields = forcing_in.fields();
    for (std::size_t field = 0; field < echoed_state_fields.size(); ++field) {
        const auto echo = tensor_values(*echoed_state_fields[field], batch * levels, "state_input_echo");
        if (std::memcmp(echo.data(), state.data() + field * static_cast<std::size_t>(batch * levels),
                        echo.size() * sizeof(double)) != 0)
            fail("direct runtime modified a state input tensor");
    }
    for (std::size_t field = 0; field < echoed_forcing_fields.size(); ++field) {
        const auto echo = tensor_values(*echoed_forcing_fields[field], batch * levels, "forcing_input_echo");
        if (std::memcmp(echo.data(), forcing.data() + field * static_cast<std::size_t>(batch * levels),
                        echo.size() * sizeof(double)) != 0)
            fail("direct runtime modified a forcing input tensor");
    }
    std::vector<double> state_out;
    for (const auto* field : result.state_out.fields()) {
        auto values = tensor_values(*field, batch * levels, "state_out");
        state_out.insert(state_out.end(), values.begin(), values.end());
    }
    std::vector<double> precip;
    for (const auto* field : {&result.rain_increment, &result.snow_increment, &result.graupel_increment}) {
        auto values = tensor_values(*field, batch, "precip");
        precip.insert(precip.end(), values.begin(), values.end());
    }
    const auto rhog = tensor_values(result.rhog, batch * levels, "rhog");
    if (std::filesystem::exists(output_path)) fail("reference output already exists");
    const int fd = ::open(output_path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (fd < 0) fail("cannot create new reference output");
    try {
        write_exact(fd, kReferenceMagic.data(), kReferenceMagic.size());
        write_u32(fd, kVersion); write_u32(fd, batch32); write_u32(fd, levels32);
        write_double(fd, dt); write_double(fd, ncmin_land); write_double(fd, ncmin_sea);
        write_exact(fd, request_sha256.data(), 64);
        write_exact(fd, &fpcr_before, sizeof(fpcr_before));
        write_exact(fd, &fpcr_after, sizeof(fpcr_after));
        const std::int32_t fe_nearest = FE_TONEAREST;
        write_exact(fd, &rounding_before, sizeof(rounding_before));
        write_exact(fd, &rounding_after, sizeof(rounding_after));
        write_exact(fd, &fe_nearest, sizeof(fe_nearest));
        auto write_vector = [&](const std::vector<double>& values) {
            write_exact(fd, values.data(), values.size() * sizeof(double));
        };
        write_vector(state); write_vector(forcing); write_vector(xland_wide);
        write_vector(state_out); write_vector(precip); write_vector(rhog);
        if (::fsync(fd) != 0) fail("reference fsync failed");
        ::close(fd);
    } catch (...) {
        ::close(fd); std::filesystem::remove(output_path); throw;
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 7 || std::string(argv[1]) != "--input" || std::string(argv[3]) != "--output" ||
            std::string(argv[5]) != "--request-sha256") {
            std::cerr << "usage: kdm6_native_fp64_value_reference --input REQUEST.bin --output NEW.bin --request-sha256 HEX64\n";
            return 2;
        }
        run(argv[2], argv[4], argv[6]);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "kdm6_native_fp64_value_reference: " << error.what() << '\n';
        return 1;
    } catch (...) {
        std::cerr << "kdm6_native_fp64_value_reference: unknown failure\n";
        return 1;
    }
}
