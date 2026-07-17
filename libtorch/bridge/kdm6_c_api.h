#ifndef KDM6_C_API_H
#define KDM6_C_API_H
//
// extern "C" ABI — Fortran ISO_C_BINDING 호출용.
// C++ 예외는 절대 경계 통과 금지. 모든 함수는 int 반환 (0 = 성공).
//
// 결정: [C3] opaque handle, [C4] caller-allocated output buffers, [C5] bitmask flags.
//

// ── Export visibility (PR3, docs/PR3_VISIBILITY_DESIGN.md) ───────────────────
// The shipped dylib hides ALL internals (kdm6::/libtorch/std) and exports ONLY
// the C ABI functions below, each marked KDM6_C_API. Build/consumer aware so
// the one header serves both: Windows marks dllexport in the producing TU
// (KDM6_C_BUILD, set only on the kdm6_c target) and dllimport in a consumer;
// macOS/Linux use the identical default-visibility attribute. Windows is NOT a
// PR3 verification target — the branch exists only to keep the header portable.
#if defined(_WIN32)
#  if defined(KDM6_C_BUILD)
#    define KDM6_C_API __declspec(dllexport)
#  else
#    define KDM6_C_API __declspec(dllimport)
#  endif
#elif defined(__GNUC__) || defined(__clang__)
#  define KDM6_C_API __attribute__((visibility("default")))
#else
#  define KDM6_C_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct kdm6_handle_t kdm6_handle_t;

// 에러 코드 (음수)
enum {
    KDM6_OK                  = 0,
    KDM6_ERR_INVALID_DIM     = -1,
    KDM6_ERR_NULL_POINTER    = -2,
    KDM6_ERR_NOT_IMPLEMENTED = -3,
    KDM6_ERR_HANDLE_CLOSED   = -4,
    KDM6_ERR_VALUE_ONLY      = -5,
    KDM6_ERR_INVALID_ARG     = -6,   // an argument is outside its documented domain
    KDM6_ERR_THREAD_CONFIG   = -7,   // libtorch/OpenMP could not be pinned to a single
                                     // thread — bitwise determinism requires 1 intra-op
                                     // AND 1 inter-op thread; the call is refused BEFORE
                                     // any tensor creation (fail-closed: handle NULL,
                                     // output buffers untouched)
    KDM6_ERR_INTERNAL        = -100,
};

// VALIDATION PRECEDENCE (kdm6_step_c / kdm6_step_ad_c): the output handle is set to NULL
// first, then arguments are checked in this order and the FIRST failure is returned:
//   1. dimensions      → KDM6_ERR_INVALID_DIM
//   2. value_only ∈ {0,1} → KDM6_ERR_INVALID_ARG
//   3. required pointers → KDM6_ERR_NULL_POINTER
//   4. param_grad_flags (step_c only) → KDM6_ERR_NOT_IMPLEMENTED
//   5. single-thread fence → KDM6_ERR_THREAD_CONFIG (AFTER all argument checks, BEFORE
//      any tensor creation): libtorch/OpenMP could not be pinned to 1 intra-op AND 1
//      inter-op thread, which bitwise determinism requires. Fail-closed — the output
//      handle stays NULL and NO output buffer is written, so a THREAD_CONFIG refusal is
//      side-effect-free and the caller's output buffers keep their pre-call values.
// So an argument-domain error (e.g. value_only=2) may be reported BEFORE a null-pointer
// error when both are present. On ANY error the output handle is left NULL.

/**
 * 한 step KDM6 호출. Fortran forward와 *동반 구동*되어 derivative 정보 산출.
 *
 * 입력 state/forcing은 Fortran-allocated float*(im, kme, jme).
 * 출력 state는 caller가 *미리 할당*한 float*(im, kme, jme)에 결과 복사.
 *
 * @param param_grad_flags  RESERVED — must be 0. Physics-parameter sensitivity
 *                          (PEAUT / NCRK1 / NCRK2 / ECCBRK gradients) is NOT yet
 *                          wired into the forward graph: kdm6_fn consumes baked-in
 *                          constants (see runtime.cpp), so a non-zero flag would
 *                          build trainable leaves that never reach the graph. To
 *                          avoid a silent "flag set, no effect" trap, any non-zero
 *                          value is REJECTED with KDM6_ERR_NOT_IMPLEMENTED. Only
 *                          STATE leaves (the 12 prognostic inputs) are
 *                          differentiable today. Bit meanings, reserved for a
 *                          future param-grad ABI: 1=PEAUT, 2=NCRK1, 4=NCRK2, 8=ECCBRK.
 * @param value_only        0/1 ONLY. 1 → graph 안 만듦(forward 정합 검증용), *handle=NULL.
 *                          0 → derivative-ready handle 반환. Any other value → KDM6_ERR_INVALID_ARG.
 * @param[out] handle       opaque handle. value_only=1이면 NULL 반환, value_only=0이면 close 필요.
 *
 * @return KDM6_OK 또는 음수 에러 코드.
 */
KDM6_C_API int kdm6_step_c(
    /* in: 12 prognostic state */
    const float* th, const float* qv, const float* qc, const float* qr,
    const float* qi, const float* qs, const float* qg,
    const float* nccn, const float* nc, const float* ni, const float* nr,
    const float* bg,
    /* in: 4 forcing */
    const float* rho, const float* pii, const float* p, const float* delz,
    /* in: dimensions, dt, flags */
    int im, int kme, int jme, double dt,
    int param_grad_flags, int value_only,
    /* out: 12 prognostic */
    float* th_out, float* qv_out, float* qc_out, float* qr_out,
    float* qi_out, float* qs_out, float* qg_out,
    float* nccn_out, float* nc_out, float* ni_out, float* nr_out,
    float* bg_out,
    /* out: opaque handle */
    kdm6_handle_t** handle,
    /* in (optional, appended): land/sea mask + per-regime ncmin scalars.
     * `xland` is a float*(im, jme) — Fortran 2-D pattern matches WRF XLAND
     * (>=1.5 → sea, else land). May be NULL → C++ falls back to the
     * pre-extension behavior (sea_mask = all true, scalar `constants::NCMIN`).
     * When non-NULL, `ncmin_land` / `ncmin_sea` are applied per-cell:
     *   ncmin_eff(i,j) = (xland(i,j) >= 1.5) ? ncmin_sea : ncmin_land
     * and injected into the C++ Phase Params' `ncmin_tensor` field.
     * See module_mp_kdm6ad.F (caller) and runtime.cpp (consumer). */
    const float* xland,
    double ncmin_land,
    double ncmin_sea,
    /* out (optional, appended): per-column sedimentation surface increments
     * [mm] for the timestep `dt`. Each is a Fortran-allocated float*(im, jme)
     * (column-major) or NULL to discard. WRF wrapper uses these to accumulate
     * RAINNCV / SNOWNCV / GRAUPELNCV / SR / RAIN / SNOW / GRAUPEL.
     * If NULL, the runtime still computes sedimentation but the increments
     * are not copied out. See module_mp_kdm6ad.F:1304-1324 reference for the
     * Fortran-side accumulation pattern. */
    float* rain_increment,
    float* snow_increment,
    float* graupel_increment,
    /* out (optional, appended): graupel density [kg m^-3] diagnostic, a
     * Fortran-allocated float*(im, kme, jme) column-major or NULL to discard.
     * Mirrors Fortran module_mp_kdm6.F:423 `diag_rhog(i,k,j)=rhox(i,k)` — the
     * last-ProgB graupel density. WRF wrapper writes this to diag_rhog/RHOPO3D. */
    float* rhog_out
);

/* ══ Stable ABI v2 (docs/PR2_ABI_V2_DESIGN.md) ═══════════════════════════════
 *
 * v1 kdm6_step_c grew by APPENDING trailing C parameters, which is not binary-
 * compatible (an old-signature caller passes undefined values). v2 moves all
 * inputs into an options struct whose growth is expressed by `struct_size`, so
 * the function signature never changes again. kdm6_step_c (v1) stays FROZEN and
 * byte-identical; kdm6_step_v2_c shares the SAME internal physics core, so the
 * two are bitwise-equivalent (pinned by test_c_abi). */

#include <stdint.h>

#define KDM6_ABI_VERSION 2u

/* Physics-variant selector (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md).
 * Selected via the append-only v2 tail field `physics_variant`; callers whose
 * struct_size ends before the field get KDM6_PHYSICS_LEGACY. v1 kdm6_step_c
 * is PERMANENTLY legacy. Unknown values → KDM6_ERR_INVALID_ARG (fail-loud). */
typedef enum {
    KDM6_PHYSICS_LEGACY = 0,
    KDM6_PHYSICS_CONSERVATIVE_INTERFACE = 1
} kdm6_physics_variant;
/* the two framing fields a valid caller MUST allocate. struct_size is read
 * first as a bare uint32_t; a value below this is rejected before abi_version
 * (offset 4) — otherwise a 4-byte caller would have abi_version read past its
 * buffer (see docs/PR2_ABI_V2_DESIGN.md §4). */
#define KDM6_STEP_V2_MIN_SIZE ((uint32_t)(2u * sizeof(uint32_t)))

typedef struct {
    /* ── ABI framing: MUST be the first two fields, never reordered/removed ── */
    uint32_t struct_size;    /* sizeof(kdm6_step_v2_args) AS THE CALLER SAW IT */
    uint32_t abi_version;    /* KDM6_ABI_VERSION the caller was built against  */

    /* ── dimensions / dt ── */
    int32_t  im, kme, jme;
    double   dt;

    /* ── control flags ── */
    int32_t  value_only;       /* 0/1 only */
    int32_t  param_grad_flags; /* RESERVED, must be 0 (as v1) */

    /* ── required inputs: 12 state + 4 forcing (Fortran (im,kme,jme) col-major) ── */
    const float *th, *qv, *qc, *qr, *qi, *qs, *qg,
                *nccn, *nc, *ni, *nr, *bg;
    const float *rho, *pii, *p, *delz;

    /* ── required outputs: 12 state (caller-allocated) ── */
    float *th_out, *qv_out, *qc_out, *qr_out, *qi_out, *qs_out, *qg_out,
          *nccn_out, *nc_out, *ni_out, *nr_out, *bg_out;

    /* ── derivative handle (out) ── */
    kdm6_handle_t** handle;

    /* ── OPTIONAL: NULL ⇒ "not provided", identical semantics to v1 ── */
    const float *xland;        /* NULL ⇒ maritime */
    double       ncmin_land, ncmin_sea;
    float       *rain_increment, *snow_increment, *graupel_increment; /* NULL ⇒ skip */
    float       *rhog_out;     /* NULL ⇒ skip */

    /* ── OPTIONAL (conservative-interface-v1 freeze-lift): physics variant.
     * Absent (smaller struct_size) or 0 ⇒ KDM6_PHYSICS_LEGACY, bitwise-
     * identical to every pre-existing call. Values outside the
     * kdm6_physics_variant enum ⇒ KDM6_ERR_INVALID_ARG. ── */
    uint32_t     physics_variant;

    /* Future fields are APPENDED here only; a smaller struct_size means the
     * caller did not supply them and the library uses their documented
     * NULL/zero default. */
} kdm6_step_v2_args;

/** The ABI version this library implements (== KDM6_ABI_VERSION at its build). */
KDM6_C_API int kdm6_get_abi_version_c(void);

/** sizeof(kdm6_step_v2_args) as the LIBRARY sees it — lets a Fortran/other
 *  caller assert its own struct layout matches at run time.
 *  WARNING: this is a library-side size DIAGNOSTIC only. Callers must NOT
 *  copy its return into their struct_size field — struct_size is the
 *  CALLER-owned half of the ABI contract and must be the caller's own
 *  compiled sizeof/c_sizeof(args). An old caller that copied a newer
 *  library's (larger) size would claim tail fields it never allocated,
 *  making the library read past the caller's buffer. */
KDM6_C_API uint32_t kdm6_step_v2_args_size_c(void);

/**
 * v2 forward entry. All inputs live in *args (see the struct + the design doc).
 * Validation precedence: args==NULL → NULL_POINTER; struct_size <
 * KDM6_STEP_V2_MIN_SIZE → INVALID_ARG (BEFORE abi_version is read); abi_version
 * major mismatch → INVALID_ARG; struct_size too small for the required fields →
 * INVALID_ARG; then the v1 checks (dims/value_only/pointers/param_grad) and the
 * PR1-A thread fence. The library reads at most min(struct_size, sizeof) bytes.
 * Same fail-closed contract as v1: *handle=NULL and no output written on error.
 * @return KDM6_OK or a negative error code.
 */
KDM6_C_API int kdm6_step_v2_c(const kdm6_step_v2_args* args);

/**
 * [DA §0.1.A] fp64 DA adjoint forward — kdm6_step_ad_c.
 *
 * The OPERATIONAL kdm6_step_c runs the native-f32 bitwise path; its gradients
 * carry f32 precision and the f32 backward can NaN at inactive-ice corners.
 * THIS entry runs the SAME physics at float64 with a gradient graph — the
 * design-default DA path (kdm6ad+da.md §0.1.A). Use the returned handle with
 * kdm6_handle_vjp_c / kdm6_handle_jvp_c for fp64 adjoints/tangents (the
 * packed derivative buffers then carry true fp64 precision, finite at the
 * ice corners).
 *
 * PACKED LAYOUT (identical to the VJP/JVP buffers — field-major sequences of
 * FORTRAN (im,kme,jme) column-major double blocks):
 *   state_in_packed / state_out_packed : 12 fields * im*kme*jme doubles,
 *       field order th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg.
 *   forcing_packed : 4 fields * im*kme*jme doubles, order rho,pii,p,delz.
 * A Fortran caller declares REAL(8) :: x(im,kme,jme,12), f(im,kme,jme,4).
 *
 * value_only=0 → *handle is a live fp64 graph handle (close after use);
 * value_only=1 → *handle = NULL (pure fp64 forward).
 * xland: optional, but when non-NULL it MUST be a Fortran column-major (im,jme)
 *   float buffer (element (i,j) at 0-based offset (i-1)+im*(j-1)), exactly as in
 *   kdm6_step_c. A raw C pointer carries no shape, so this entry CANNOT
 *   disambiguate a flat batch-order (i*jme+j) buffer — passing one silently
 *   scrambles the land/sea mask when im>1 and jme>1. NULL → default (all-sea).
 *   The NULL/default-xland path is reachable from C callers ONLY: the public
 *   Fortran wrapper kdm6_step_ad (kdm6_iso_c) takes xland as a REQUIRED
 *   assumed-shape argument and always passes it — KIM/WRF hosts always have
 *   XLAND, so no optional variant is provided (Codex review finding 3).
 *
 * NOTE: this entry does NOT touch the operational path — it is additive; the
 * f32 kdm6_step_c remains bitwise-locked.
 */
KDM6_C_API int kdm6_step_ad_c(
    const double* state_in_packed,
    const double* forcing_packed,
    int im, int kme, int jme, double dt,
    int value_only,
    double* state_out_packed,
    kdm6_handle_t** handle,
    const float* xland,
    double ncmin_land,
    double ncmin_sea);

/**
 * VJP — J^T @ u. 4D-Var adjoint 용.
 *
 * PACKED BUFFER LAYOUT (ABI contract — u_packed / grad_out_packed, and the
 * JVP v_packed / tangent_out_packed below):
 *   - total size  = 12 * im * kme * jme doubles, caller-allocated.
 *   - field-major: 12 consecutive blocks in State field order
 *       th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg
 *     (the n-th field, n = 1..12 in that order, starts at 0-based double
 *     offset (n-1) * im*kme*jme).
 *   - WITHIN each block: FORTRAN (im, kme, jme) COLUMN-MAJOR — the SAME
 *     convention as every state/forcing array in kdm6_step_c. Concretely,
 *     each block is bit-for-bit a Fortran array
 *         REAL(8) :: A(im, kme, jme)
 *     whose element A(i,k,j) — 1-BASED Fortran indices, i=1..im, k=1..kme,
 *     j=1..jme — sits at 0-based double offset
 *         (i-1) + im*(k-1) + im*kme*(j-1)
 *     within the block. (For C callers with 0-based i,k,j: i + im*k +
 *     im*kme*j.) A Fortran caller therefore declares
 *         REAL(8) :: u(im, kme, jme, 12)
 *     fills u(:,:,:,n) per field in the order above, and passes u — exactly
 *     like its state arrays; no knowledge of the internal (B,K) tensor layout
 *     is required. The bridge performs the layout staging internally.
 *   - im/kme/jme are the dimensions captured in the handle at kdm6_step_c time.
 *
 * @return KDM6_OK 또는 KDM6_ERR_VALUE_ONLY / HANDLE_CLOSED / NOT_IMPLEMENTED.
 *
 * NOTE: the derivative (VJP/JVP) packed arrays stay `double` ON PURPOSE — only the
 * operational state/forcing ABI (kdm6_step_c) went native float32 to match Fortran
 * mp37 (RWORDSIZE=4). 4D-Var adjoint/tangent precision must remain fp64 (the
 * differentiable oracle's precision); float32 gradient buffers would degrade it.
 *
 * CONTRACT — which handle to use for what:
 *   - A handle from kdm6_step_c(... value_only=0 ...) records the OPERATIONAL float32
 *     graph. Its VJP/JVP is a MECHANICS / DIAGNOSTICS path: correct packed layout and
 *     lifecycle, gradients at f32 precision, but **finiteness is NOT guaranteed**. The f32
 *     backward can underflow at inactive-ice corners and the NaN propagates to whatever
 *     inputs are graph-connected (which fields exactly is f32-rounding/toolchain dependent).
 *     Do NOT rely on these gradients for assimilation.
 *   - For reliable, fully-finite fp64 adjoints/tangents use a handle from kdm6_step_ad_c
 *     (the DA design default, kdm6ad+da.md §0.1.A) — same VJP/JVP calls, fp64 graph.
 */
KDM6_C_API int kdm6_handle_vjp_c(kdm6_handle_t* h,
                      const double* u_packed,
                      double* grad_out_packed);

/**
 * JVP — J @ v (double-VJP/Pearlmutter route internally). EnKF perturbation 용.
 * v_packed / tangent_out_packed use the SAME packed layout as the VJP above
 * (field-major × Fortran (im,kme,jme) column-major blocks, fp64).
 */
KDM6_C_API int kdm6_handle_jvp_c(kdm6_handle_t* h,
                      const double* v_packed,
                      double* tangent_out_packed);

/**
 * Handle 닫기 — 자원 해제. Fortran 측이 매 step 후 *반드시* 호출해야 함.
 * NULL handle은 이미 닫힌 상태로 간주하고 KDM6_OK를 반환한다.
 *
 * WARNING (by-value form): this frees `h` (delete). AFTER this call the pointer
 * `h` is DANGLING — the caller MUST discard it and must NOT reuse it for any
 * further vjp/jvp/close call. Because the wrapper object itself is freed, a
 * reuse does NOT return KDM6_ERR_HANDLE_CLOSED; it is undefined behavior
 * (use-after-free). Prefer kdm6_handle_closep_c below, which nulls the caller's
 * pointer so accidental reuse is caught as a NULL (→ KDM6_OK / no-op) instead.
 */
KDM6_C_API int kdm6_handle_close_c(kdm6_handle_t* h);

/**
 * Handle 닫기 (pointer-nulling form — RECOMMENDED). Frees `*hp` and sets
 * `*hp = NULL`, so the caller's handle variable can never dangle. Idempotent:
 * `hp == NULL` or `*hp == NULL` is a no-op returning KDM6_OK. The Fortran
 * wrapper kdm6_handle_close (kdm6_iso_c) binds to THIS entry with an
 * intent(inout) c_ptr, guaranteeing the Fortran handle is reset to C_NULL_PTR.
 */
KDM6_C_API int kdm6_handle_closep_c(kdm6_handle_t** hp);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // KDM6_C_API_H
