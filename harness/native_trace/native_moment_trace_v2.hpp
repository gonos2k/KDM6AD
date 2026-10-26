// Private, value-only instrumentation. Not part of the operational C ABI.
#pragma once

#include <array>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace kdm6_moment_trace_v2 {

struct Context {
    int call = 0, step = 0;
    int its = 0, ite = 0, kts = 0, kte = 0, jts = 0, jte = 0;
};

inline thread_local Context context;

inline bool enabled() {
    const char* directory = std::getenv("KDM6AD_MOMENT_TRACE_V2_DIR");
    return directory && *directory;
}

inline uint64_t bits(double value) {
    uint64_t result;
    static_assert(sizeof(result) == sizeof(value), "requires IEEE binary64 storage");
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

struct Writer {
    std::FILE* stream = nullptr;
    int last_call = 0;
    ~Writer() { if (stream) std::fclose(stream); }

    void open_new() {
        const char* directory = std::getenv("KDM6AD_MOMENT_TRACE_V2_DIR");
        if (!directory || !*directory) throw std::runtime_error("missing moment trace directory");
        const std::string path = std::string(directory) + "/kernel.hex";
        const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0) throw std::runtime_error("moment trace requires a fresh kernel.hex");
        stream = ::fdopen(fd, "w");
        if (!stream) {
            ::close(fd);
            throw std::runtime_error("cannot open moment trace stream");
        }
        if (std::fprintf(stream, "# KDM6AD_MOMENT_TRACE_V2\n") < 0)
            throw std::runtime_error("cannot write moment trace magic");
    }
};

// qc/nc are contiguous (batch, levels), batch=(i-its)*jme+(j-jts).
// Only read these pointers inside the explicit value-only C entry.
inline void record(const char* stage, const double* qc, const double* nc,
                   int im, int km, int jm, double dt, double land, double sea) {
    if (!enabled()) return;
    const auto& c = context;
    if (c.call < 1 || c.step < 1 || im != c.ite - c.its + 1 ||
        km != c.kte - c.kts + 1 || jm != c.jte - c.jts + 1)
        throw std::runtime_error("moment trace context differs from actual C ABI shape");
    static thread_local Writer writer;
    if (!writer.stream) writer.open_new();
    const bool input = std::strcmp(stage, "FP64_INPUT") == 0;
    if (input) {
        if (c.call != writer.last_call + 1)
            throw std::runtime_error("noncontiguous moment trace call ordinal");
        writer.last_call = c.call;
        if (std::fprintf(writer.stream,
            "CALL %d %d %d %d %d %d %d %d %d %d %d %016" PRIX64 " %016" PRIX64 " %016" PRIX64 "\n",
            c.call, c.step, c.its, c.ite, c.kts, c.kte, c.jts, c.jte,
            im, km, jm, bits(dt), bits(land), bits(sea)) < 0)
            throw std::runtime_error("cannot write moment trace call header");
    } else if (std::strcmp(stage, "FP64_OUTPUT") != 0 || c.call != writer.last_call) {
        throw std::runtime_error("unpaired moment trace output");
    }
    constexpr std::array<std::array<int, 2>, 3> targets{{{155, 25}, {221, 63}, {91, 94}}};
    for (const auto& target : targets) {
        const int i = target[0], j = target[1];
        if (i < c.its || i > c.ite || j < c.jts || j > c.jte) continue;
        const int64_t batch = int64_t(i - c.its) * jm + j - c.jts;
        for (int k = c.kts; k <= c.kte; ++k) {
            const int64_t offset = batch * km + k - c.kts;
            if (std::fprintf(writer.stream, "VAL %d %s %d %d %d f64 QC %016" PRIX64 "\n",
                    c.call, stage, i, k, j, bits(qc[offset])) < 0 ||
                std::fprintf(writer.stream, "VAL %d %s %d %d %d f64 NC %016" PRIX64 "\n",
                    c.call, stage, i, k, j, bits(nc[offset])) < 0)
                throw std::runtime_error("cannot write moment trace state");
        }
    }
    if (std::fflush(writer.stream) != 0)
        throw std::runtime_error("cannot flush moment trace state");
}

} // namespace kdm6_moment_trace_v2

// Extra symbol exists only in the isolated instrumentation build.
extern "C" __attribute__((visibility("default")))
void kdm6_moment_trace_context_c(int call, int step, int its, int ite,
                                           int kts, int kte, int jts, int jte) noexcept {
    kdm6_moment_trace_v2::context = {call, step, its, ite, kts, kte, jts, jte};
}
