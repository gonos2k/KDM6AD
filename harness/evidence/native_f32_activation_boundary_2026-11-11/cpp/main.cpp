#include <dlfcn.h>
#include "kdm6_c_api.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int kLevels = 39;
constexpr int kStateFields = 12;
constexpr int kForcingFields = 4;
constexpr std::size_t kInputWords = (kStateFields + kForcingFields) * kLevels;
constexpr int kTargetLevel = 15;  // level 16, bottom-first packed native input

using Kdm6StepC = decltype(&kdm6_step_c);

void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}

std::uint32_t float_word(float value) {
    std::uint32_t word = 0;
    static_assert(sizeof(word) == sizeof(value));
    std::memcpy(&word, &value, sizeof(word));
    return word;
}

std::string word_hex(float value) {
    std::ostringstream out;
    out << std::hex << std::setw(8) << std::setfill('0') << float_word(value);
    return out.str();
}

void emit_words(std::ostream& out, const float* values, std::size_t count) {
    out << '[';
    for (std::size_t i = 0; i < count; ++i) {
        if (i) out << ',';
        out << '"' << word_hex(values[i]) << '"';
    }
    out << ']';
}

struct Input {
    std::array<double, kInputWords> source_f64{};
    std::array<float, kStateFields * kLevels> state{};
    std::array<float, kForcingFields * kLevels> forcing{};
    float xland = 0.0f;
    double dt = 0.0;

    explicit Input(const std::filesystem::path& path) {
        std::ifstream in(path, std::ios::binary);
        require(static_cast<bool>(in), "cannot open input.bin");
        char magic[15]{};
        in.read(magic, sizeof(magic));
        require(in.gcount() == static_cast<std::streamsize>(sizeof(magic)) &&
                    std::memcmp(magic, "KDM6_PRE2_INPUT", sizeof(magic)) == 0,
                "input magic mismatch");
        in.read(reinterpret_cast<char*>(source_f64.data()),
                static_cast<std::streamsize>(sizeof(double) * source_f64.size()));
        require(static_cast<bool>(in), "truncated state/forcing payload");
        in.read(reinterpret_cast<char*>(&xland), sizeof(xland));
        in.read(reinterpret_cast<char*>(&dt), sizeof(dt));
        require(static_cast<bool>(in) && in.peek() == EOF, "unexpected input.bin length");
        for (std::size_t i = 0; i < source_f64.size(); ++i) {
            require(std::isfinite(source_f64[i]), "nonfinite source f64 value");
            const float value = static_cast<float>(source_f64[i]);
            require(std::isfinite(value) && static_cast<double>(value) == source_f64[i],
                    "source f64 input is not exactly REAL4 representable");
            if (i < state.size()) state[i] = value;
            else forcing[i - state.size()] = value;
        }
        require(xland == 2.0f && dt == 20.0, "unexpected native column controls");
    }
};

struct Options {
    std::filesystem::path library;
    std::filesystem::path input;
    std::filesystem::path output;
    std::string axis = "baseline";
    std::string word;
};

Options parse_args(int argc, char** argv) {
    Options out;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        require(i + 1 < argc, "missing value for " + key);
        const std::string value = argv[++i];
        if (key == "--library") out.library = value;
        else if (key == "--input") out.input = value;
        else if (key == "--output") out.output = value;
        else if (key == "--axis") out.axis = value;
        else if (key == "--word") out.word = value;
        else throw std::runtime_error("unknown argument: " + key);
    }
    require(!out.library.empty() && !out.input.empty() && !out.output.empty(),
            "usage: native_f32_cabi_probe --library DSO --input input.bin --output NEW.json [--axis baseline|th16|qv16 --word 8_HEX_DIGITS]");
    require(out.axis == "baseline" || out.axis == "th16" || out.axis == "qv16",
            "axis must be baseline, th16, or qv16");
    require((out.axis == "baseline") == out.word.empty(),
            "baseline omits --word; TH/QV overrides require --word");
    return out;
}

void apply_override(Input& input, const Options& options) {
    if (options.axis == "baseline") return;
    require(options.word.size() == 8, "REAL4 --word must contain exactly 8 hex digits");
    std::uint32_t word = 0;
    std::istringstream in(options.word);
    in >> std::hex >> word;
    require(static_cast<bool>(in) && in.eof(), "invalid REAL4 --word");
    float value = 0.0f;
    std::memcpy(&value, &word, sizeof(value));
    require(std::isfinite(value), "override must be finite");
    const std::size_t index = options.axis == "th16" ? kTargetLevel : kLevels + kTargetLevel;
    input.state[index] = value;
}

void run(const Options& options) {
    require(!std::filesystem::exists(options.output), "refusing to overwrite output");
    Input input(options.input);
    apply_override(input, options);

    void* handle = dlopen(options.library.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) throw std::runtime_error(std::string("dlopen failed: ") + dlerror());
    dlerror();
    auto step = reinterpret_cast<Kdm6StepC>(dlsym(handle, "kdm6_step_c"));
    const char* symbol_error = dlerror();
    require(symbol_error == nullptr && step != nullptr,
            std::string("dlsym(kdm6_step_c) failed: ") + (symbol_error ? symbol_error : "null symbol"));

    std::array<std::array<float, kLevels>, kStateFields> output{};
    std::array<float, 3> precip{};
    std::array<float, kLevels> rhog{};
    kdm6_handle_t* ad_handle = nullptr;
    const int rc = step(
        input.state.data() + 0 * kLevels, input.state.data() + 1 * kLevels,
        input.state.data() + 2 * kLevels, input.state.data() + 3 * kLevels,
        input.state.data() + 4 * kLevels, input.state.data() + 5 * kLevels,
        input.state.data() + 6 * kLevels, input.state.data() + 7 * kLevels,
        input.state.data() + 8 * kLevels, input.state.data() + 9 * kLevels,
        input.state.data() + 10 * kLevels, input.state.data() + 11 * kLevels,
        input.forcing.data() + 0 * kLevels, input.forcing.data() + 1 * kLevels,
        input.forcing.data() + 2 * kLevels, input.forcing.data() + 3 * kLevels,
        1, kLevels, 1, input.dt, 0, 1,
        output[0].data(), output[1].data(), output[2].data(), output[3].data(),
        output[4].data(), output[5].data(), output[6].data(), output[7].data(),
        output[8].data(), output[9].data(), output[10].data(), output[11].data(),
        &ad_handle, &input.xland, 10.0, 10.0,
        precip.data(), precip.data() + 1, precip.data() + 2, rhog.data());
    require(rc == 0, "kdm6_step_c failed with rc=" + std::to_string(rc));
    require(ad_handle == nullptr, "value_only C ABI returned a non-null AD handle");

    std::ofstream out(options.output, std::ios::out | std::ios::binary);
    require(static_cast<bool>(out), "cannot create output JSON");
    out << "{\"schema\":\"kdm6.native_f32_activation_probe_call.v1\",\"axis\":\""
        << options.axis << "\",\"override_word\":\"" << options.word
        << "\",\"library\":\"" << options.library.string()
        << "\",\"rc\":" << rc << ",\"value_only\":1,\"handle_null\":true"
        << ",\"shape\":[1,39,1],\"dt_s\":20,\"xland\":2,\"ncmin_land\":10,\"ncmin_sea\":10"
        << ",\"source_state_f32_words\":";
    emit_words(out, input.state.data(), input.state.size());
    out << ",\"source_forcing_f32_words\":";
    emit_words(out, input.forcing.data(), input.forcing.size());
    out << ",\"state_output_f32_words\":[";
    for (int field = 0; field < kStateFields; ++field) {
        if (field) out << ',';
        emit_words(out, output[field].data(), output[field].size());
    }
    out << "],\"precip_increment_f32_words\":";
    emit_words(out, precip.data(), precip.size());
    out << ",\"rhog_output_f32_words\":";
    emit_words(out, rhog.data(), rhog.size());
    out << "}\n";
    out.close();
    require(static_cast<bool>(out), "failed writing output JSON");
    dlclose(handle);
}
}  // namespace

int main(int argc, char** argv) {
    try {
        run(parse_args(argc, argv));
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "native_f32_cabi_probe: " << error.what() << '\n';
        return 2;
    }
}
