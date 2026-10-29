/* A small C99 bridge for the active hardware rounding-mode check. */
#include <fenv.h>
#include <stdint.h>

#if defined(__x86_64__) || defined(__i386__)
#include <xmmintrin.h>
#endif

static int qnc_hardware_nearest(void) {
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    return (fpcr & (UINT64_C(3) << 22)) == 0;
#elif defined(__x86_64__) || defined(__i386__)
    return (_mm_getcsr() & 0x6000u) == 0;
#else
    return 0;
#endif
}

int qnc_rounding_is_nearest(void) {
    return fegetround() == FE_TONEAREST && qnc_hardware_nearest();
}

int qnc_gradual_underflow_enabled(void) {
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    /* FZ flushes results, FZ16 handles half, FEAT_AFP FIZ (bit 0)
       can flush subnormal inputs, and FEAT_AFP AH (bit 1) changes
       corner-case arithmetic. Reject all four even if a feature bit
       is reserved on the current CPU. */
    return (fpcr & ((UINT64_C(1) << 24) | (UINT64_C(1) << 19) |
                    UINT64_C(3))) == 0;
#elif defined(__x86_64__) || defined(__i386__)
    /* MXCSR bit 15 is FTZ and bit 6 is DAZ. */
    return (_mm_getcsr() & 0x8040u) == 0;
#else
    return 0;
#endif
}

int qnc_rounding_downward_code(void) {
    return FE_DOWNWARD;
}

#ifdef QNC_TEST_ROUNDING
int qnc_test_set_ftz(int enabled) {
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    const int previous = (int)((fpcr >> 24) & UINT64_C(1));
    fpcr = enabled ? fpcr | (UINT64_C(1) << 24) : fpcr & ~(UINT64_C(1) << 24);
    __asm__ volatile("msr fpcr, %0" : : "r"(fpcr));
    return previous;
#elif defined(__x86_64__) || defined(__i386__)
    unsigned int csr = _mm_getcsr();
    const int previous = (int)((csr >> 15) & 1u);
    csr = enabled ? csr | 0x8000u : csr & ~0x8000u;
    _mm_setcsr(csr);
    return previous;
#else
    (void)enabled;
    return -1;
#endif
}

int qnc_test_set_fiz(int enabled) {
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    const int previous = (int)(fpcr & UINT64_C(1));
    fpcr = enabled ? fpcr | UINT64_C(1) : fpcr & ~UINT64_C(1);
    __asm__ volatile("msr fpcr, %0" : : "r"(fpcr));
    uint64_t observed;
    __asm__ volatile("mrs %0, fpcr" : "=r"(observed));
    if ((observed & UINT64_C(1)) != (enabled ? UINT64_C(1) : UINT64_C(0))) {
        return -1; /* FEAT_AFP/FIZ not writable: no test assertion possible. */
    }
    return previous;
#else
    (void)enabled;
    return -1;
#endif
}

int qnc_test_set_ah(int enabled) {
#if defined(__aarch64__) || defined(__arm64__)
    uint64_t fpcr;
    __asm__ volatile("mrs %0, fpcr" : "=r"(fpcr));
    const int previous = (int)((fpcr >> 1) & UINT64_C(1));
    fpcr = enabled ? fpcr | UINT64_C(2) : fpcr & ~UINT64_C(2);
    __asm__ volatile("msr fpcr, %0" : : "r"(fpcr));
    uint64_t observed;
    __asm__ volatile("mrs %0, fpcr" : "=r"(observed));
    if ((observed & UINT64_C(2)) != (enabled ? UINT64_C(2) : UINT64_C(0))) {
        return -1;
    }
    return previous;
#else
    (void)enabled;
    return -1;
#endif
}
#endif
