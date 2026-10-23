#include "kdm6/runtime.h"

#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

// Binary protocol (all integers and IEEE binary64 values little-endian):
// request = magic[8], version:u32, levels:u32, dt/xland/ncmin_land/ncmin_sea:f64,
//           state[12,levels] then forcing[4,levels], both field-major;
// response = magic[8], version:u32, levels:u32, echoed state, echoed forcing,
//            state_out, total_precip_mm/snow_ice_mm/graupel_mm.
// State and forcing row order is exactly State::fields()/Forcing::fields().
constexpr std::array<char, 8> kInputMagic{{'K', '6', 'B', 'U', 'D', 'G', '1', '\0'}};
constexpr std::array<char, 8> kOutputMagic{{'K', '6', 'B', 'O', 'U', 'T', '1', '\0'}};
constexpr std::uint32_t kVersion = 1;
constexpr std::uint32_t kStateFields = 12;
constexpr std::uint32_t kForcingFields = 4;
constexpr std::uint32_t kPrecipFields = 3;
constexpr std::uint32_t kMaxLevels = 256;
constexpr std::size_t kInputHeaderBytes = 8 + 2 * sizeof(std::uint32_t) + 4 * sizeof(double);
constexpr std::size_t kOutputHeaderBytes = 8 + 2 * sizeof(std::uint32_t);

static_assert(sizeof(double) == sizeof(std::uint64_t), "protocol requires binary64");
static_assert(std::numeric_limits<double>::is_iec559, "protocol requires IEEE-754 binary64");

bool host_is_little_endian() {
    const std::uint16_t one = 1;
    return *reinterpret_cast<const unsigned char*>(&one) == 1;
}

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

std::vector<unsigned char> read_request(const std::filesystem::path& path) {
    struct stat st {};
    if (::stat(path.c_str(), &st) != 0) fail("cannot stat request: " + path.string());
    if (!S_ISREG(st.st_mode)) fail("request must be a regular file");
    if (st.st_size < 0 || static_cast<std::uint64_t>(st.st_size) < kInputHeaderBytes) {
        fail("request is shorter than the fixed header");
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) fail("cannot open request: " + path.string());
    std::array<unsigned char, kInputHeaderBytes> header{};
    in.read(reinterpret_cast<char*>(header.data()), static_cast<std::streamsize>(header.size()));
    if (in.gcount() != static_cast<std::streamsize>(header.size())) fail("truncated request header");
    if (std::memcmp(header.data(), kInputMagic.data(), kInputMagic.size()) != 0) {
        fail("bad request magic");
    }

    std::uint32_t version = 0;
    std::uint32_t levels = 0;
    std::memcpy(&version, header.data() + 8, sizeof(version));
    std::memcpy(&levels, header.data() + 12, sizeof(levels));
    if (version != kVersion) fail("unsupported request version");
    if (levels == 0 || levels > kMaxLevels) fail("level count is outside 1..256");

    const std::uint64_t payload_doubles =
        static_cast<std::uint64_t>(kStateFields + kForcingFields) * levels;
    const std::uint64_t expected_bytes = kInputHeaderBytes + payload_doubles * sizeof(double);
    if (static_cast<std::uint64_t>(st.st_size) != expected_bytes) {
        fail("request length does not match its declared level count");
    }

    std::vector<unsigned char> bytes(static_cast<std::size_t>(expected_bytes));
    std::memcpy(bytes.data(), header.data(), header.size());
    in.read(reinterpret_cast<char*>(bytes.data() + header.size()),
            static_cast<std::streamsize>(bytes.size() - header.size()));
    if (in.gcount() != static_cast<std::streamsize>(bytes.size() - header.size())) {
        fail("truncated request payload");
    }
    char extra = 0;
    if (in.get(extra)) fail("request contains trailing bytes");
    return bytes;
}

double get_double(const std::vector<unsigned char>& bytes, std::size_t offset) {
    double value = 0.0;
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    return value;
}

void append_u32(std::vector<unsigned char>& out, std::uint32_t value) {
    const auto* p = reinterpret_cast<const unsigned char*>(&value);
    out.insert(out.end(), p, p + sizeof(value));
}

void append_double(std::vector<unsigned char>& out, double value) {
    const auto* p = reinterpret_cast<const unsigned char*>(&value);
    out.insert(out.end(), p, p + sizeof(value));
}

std::vector<double> tensor_values(const torch::Tensor& tensor, std::uint32_t levels,
                                  const char* label) {
    auto t = tensor.contiguous().view({-1});
    if (t.numel() != static_cast<std::int64_t>(levels)) {
        fail(std::string("runtime changed ") + label + " shape");
    }
    std::vector<double> values(levels);
    std::memcpy(values.data(), t.data_ptr<double>(), levels * sizeof(double));
    return values;
}

std::vector<unsigned char> make_output(
    std::uint32_t levels,
    const std::vector<double>& state_in,
    const std::vector<double>& forcing_in,
    const std::vector<double>& state_out,
    const std::array<double, kPrecipFields>& precip) {
    std::vector<unsigned char> out;
    out.reserve(kOutputHeaderBytes +
                (state_in.size() + forcing_in.size() + state_out.size() + precip.size()) * sizeof(double));
    out.insert(out.end(), kOutputMagic.begin(), kOutputMagic.end());
    append_u32(out, kVersion);
    append_u32(out, levels);
    for (double x : state_in) append_double(out, x);
    for (double x : forcing_in) append_double(out, x);
    for (double x : state_out) append_double(out, x);
    for (double x : precip) append_double(out, x);
    return out;
}

void write_all(int fd, const unsigned char* data, std::size_t size) {
    std::size_t done = 0;
    while (done < size) {
        const ssize_t n = ::write(fd, data + done, size - done);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) fail("failed while writing temporary result");
        done += static_cast<std::size_t>(n);
    }
}

void publish_no_clobber(const std::filesystem::path& path,
                        const std::vector<unsigned char>& bytes) {
    if (std::filesystem::exists(path)) fail("result path already exists");
    auto parent = path.parent_path();
    if (parent.empty()) parent = ".";
    if (!std::filesystem::is_directory(parent)) fail("result parent directory does not exist");

    const auto stem = path.filename().string();
    std::filesystem::path temp;
    int fd = -1;
    for (unsigned int attempt = 0; attempt < 100; ++attempt) {
        temp = parent / ("." + stem + ".tmp." + std::to_string(::getpid()) + "." +
                         std::to_string(attempt));
        fd = ::open(temp.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd >= 0) break;
        if (errno != EEXIST) fail("cannot create temporary result");
    }
    if (fd < 0) fail("cannot reserve a temporary result filename");

    bool temp_exists = true;
    try {
        write_all(fd, bytes.data(), bytes.size());
        if (::fsync(fd) != 0) fail("cannot sync temporary result");
        if (::close(fd) != 0) {
            fd = -1;
            fail("cannot close temporary result");
        }
        fd = -1;
        // A hard-link publish is atomic and fails if another process created
        // the destination after the initial existence check.
        if (::link(temp.c_str(), path.c_str()) != 0) fail("cannot publish result without clobbering");
        if (::unlink(temp.c_str()) != 0) fail("result published but temporary link cleanup failed");
        temp_exists = false;
    } catch (...) {
        if (fd >= 0) ::close(fd);
        if (temp_exists) ::unlink(temp.c_str());
        throw;
    }
}

void run(const std::filesystem::path& input_path, const std::filesystem::path& output_path) {
    if (!host_is_little_endian()) fail("this build requires a little-endian host");
    const auto bytes = read_request(input_path);

    std::uint32_t levels = 0;
    std::memcpy(&levels, bytes.data() + 12, sizeof(levels));
    std::array<double, 4> meta{};
    for (std::size_t n = 0; n < meta.size(); ++n) {
        meta[n] = get_double(bytes, 16 + n * sizeof(double));
        if (!std::isfinite(meta[n])) fail("request metadata contains NaN or infinity");
    }
    const double dt = meta[0];
    const double xland_value = meta[1];
    const double ncmin_land = meta[2];
    const double ncmin_sea = meta[3];
    if (!(dt > 0.0)) fail("dt must be positive");
    if (!(xland_value == 1.0 || xland_value == 2.0)) fail("xland must be 1 (land) or 2 (sea)");
    if (ncmin_land < 0.0 || ncmin_sea < 0.0) fail("ncmin thresholds must be nonnegative");

    const std::size_t state_size = static_cast<std::size_t>(kStateFields) * levels;
    const std::size_t forcing_size = static_cast<std::size_t>(kForcingFields) * levels;
    std::vector<double> state_values(state_size);
    std::vector<double> forcing_values(forcing_size);
    const std::size_t payload_offset = kInputHeaderBytes;
    for (std::size_t n = 0; n < state_size; ++n) {
        state_values[n] = get_double(bytes, payload_offset + n * sizeof(double));
        if (!std::isfinite(state_values[n])) fail("state payload contains NaN or infinity");
    }
    for (std::size_t n = 0; n < forcing_size; ++n) {
        forcing_values[n] = get_double(bytes, payload_offset + (state_size + n) * sizeof(double));
        if (!std::isfinite(forcing_values[n])) fail("forcing payload contains NaN or infinity");
    }
    // The runtime's thermodynamic forcing must be physically usable. These
    // checks do not alter values or impose a new projection on the state.
    for (std::uint32_t k = 0; k < levels; ++k) {
        if (!(forcing_values[k] > 0.0) || !(forcing_values[levels + k] > 0.0) ||
            !(forcing_values[2 * levels + k] > 0.0) || !(forcing_values[3 * levels + k] > 0.0)) {
            fail("rho, pii, p, and delz must be positive at every level");
        }
    }

    auto options = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
    auto field = [&](const std::vector<double>& values, std::size_t offset) {
        return torch::from_blob(const_cast<double*>(values.data() + offset),
                                {1, static_cast<std::int64_t>(levels)}, options).clone();
    };
    kdm6::State state;
    auto sf = state.fields();
    for (std::size_t n = 0; n < sf.size(); ++n) *sf[n] = field(state_values, n * levels);
    kdm6::Forcing forcing;
    auto ff = forcing.fields();
    for (std::size_t n = 0; n < ff.size(); ++n) *ff[n] = field(forcing_values, n * levels);
    auto xland = torch::full({1}, xland_value, options);
    auto params = kdm6::make_parameters(0, torch::kCPU, torch::kFloat64);

    // One same-call legacy/value-only forward. Precipitation fields are emitted
    // as returned: total_precip_mm already covers rain + snow + graupel + ice.
    kdm6::FnResult result;
    {
        torch::NoGradGuard no_grad;
        result = kdm6::kdm6_fn(state, forcing, params, dt, xland,
                               ncmin_land, ncmin_sea, kdm6::PhysicsOptions{}, false);
    }

    // The call is functional by contract. Verify every operand remains exactly
    // the binary64 payload supplied to it before publishing the echoed inputs.
    auto in_state_fields = state.fields();
    for (std::size_t n = 0; n < in_state_fields.size(); ++n) {
        const auto actual = tensor_values(*in_state_fields[n], levels, "state input");
        if (std::memcmp(actual.data(), state_values.data() + n * levels,
                        levels * sizeof(double)) != 0) {
            fail("runtime modified a state input tensor");
        }
    }
    auto in_forcing_fields = forcing.fields();
    for (std::size_t n = 0; n < in_forcing_fields.size(); ++n) {
        const auto actual = tensor_values(*in_forcing_fields[n], levels, "forcing input");
        if (std::memcmp(actual.data(), forcing_values.data() + n * levels,
                        levels * sizeof(double)) != 0) {
            fail("runtime modified a forcing input tensor");
        }
    }

    std::vector<double> output_state(state_size);
    const auto out_fields = result.state_out.fields();
    for (std::size_t n = 0; n < out_fields.size(); ++n) {
        const auto t = out_fields[n]->contiguous().view({-1});
        if (t.numel() != static_cast<std::int64_t>(levels)) fail("runtime returned a state field with wrong size");
        const auto* p = t.data_ptr<double>();
        for (std::uint32_t k = 0; k < levels; ++k) {
            const double v = p[k];
            if (!std::isfinite(v)) fail("runtime returned a nonfinite state value");
            output_state[n * levels + k] = v;
        }
    }
    const std::array<torch::Tensor, 3> precip_tensors{{
        result.rain_increment, result.snow_increment, result.graupel_increment}};
    std::array<double, kPrecipFields> precip{};
    for (std::size_t n = 0; n < precip_tensors.size(); ++n) {
        auto t = precip_tensors[n].contiguous().view({-1});
        if (t.numel() != 1) fail("runtime returned a precipitation diagnostic with wrong size");
        precip[n] = t.item<double>();
        if (!std::isfinite(precip[n])) fail("runtime returned a nonfinite precipitation diagnostic");
    }
    publish_no_clobber(output_path,
                       make_output(levels, state_values, forcing_values, output_state, precip));
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 5 || std::string(argv[1]) != "--input" || std::string(argv[3]) != "--output") {
            std::cerr << "usage: kdm6_column_budget --input REQUEST.bin --output RESULT.bin\n";
            return 2;
        }
        run(argv[2], argv[4]);
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "kdm6_column_budget: " << e.what() << '\n';
        return 1;
    } catch (...) {
        std::cerr << "kdm6_column_budget: unknown failure\n";
        return 1;
    }
}
