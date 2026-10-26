// Test-only floating-environment probe for the native fp64-value bridge.
// This is separate from the C ABI and is called on the Python test thread.
#include <cfenv>
#include <cstdint>

extern "C" int kdm6_fp_env_snapshot(std::uint64_t* fpcr, int* rounding_mode) {
    if (fpcr == nullptr || rounding_mode == nullptr) return -1;
#if defined(__aarch64__)
    std::uint64_t value = 0;
    asm volatile("mrs %0, fpcr" : "=r"(value));
    *fpcr = value;
#else
    *fpcr = UINT64_MAX;  // raw FPCR is only defined on AArch64.
#endif
    *rounding_mode = std::fegetround();
    return *rounding_mode == -1 ? -2 : 0;
}

extern "C" int kdm6_fe_tonearest() { return FE_TONEAREST; }
