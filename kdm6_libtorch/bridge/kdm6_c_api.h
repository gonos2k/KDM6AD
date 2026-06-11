#ifndef KDM6_C_API_H
#define KDM6_C_API_H
//
// extern "C" ABI — Fortran ISO_C_BINDING 호출용.
// C++ 예외는 절대 경계 통과 금지. 모든 함수는 int 반환 (0 = 성공).
//
// 결정: [C3] opaque handle, [C4] caller-allocated output buffers, [C5] bitmask flags.
//

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
    KDM6_ERR_INTERNAL        = -100,
};

/**
 * 한 step KDM6 호출. Fortran forward와 *동반 구동*되어 derivative 정보 산출.
 *
 * 입력 state/forcing은 Fortran-allocated float*(im, kme, jme).
 * 출력 state는 caller가 *미리 할당*한 float*(im, kme, jme)에 결과 복사.
 *
 * @param param_grad_flags  Bitwise OR of:
 *                            1 = PEAUT, 2 = NCRK1, 4 = NCRK2, 8 = ECCBRK, 15 = ALL
 *                          0이면 모든 파라미터 frozen.
 * @param value_only        1이면 graph 안 만듦 (forward 정합 검증용). 0이면 derivative-ready handle 반환.
 * @param[out] handle       opaque handle. value_only=1이면 NULL 반환, value_only=0이면 close 필요.
 *
 * @return KDM6_OK 또는 음수 에러 코드.
 */
int kdm6_step_c(
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
    float* graupel_increment
);

/**
 * VJP — J^T @ u. 4D-Var adjoint 용.
 *
 * `u_packed`는 12 필드 × (im*jme*kme) double의 *연결된* 배열.
 * `grad_out_packed`도 동일 layout, caller-allocated.
 *
 * @return KDM6_OK 또는 KDM6_ERR_VALUE_ONLY / HANDLE_CLOSED / NOT_IMPLEMENTED.
 *
 * NOTE: the derivative (VJP/JVP) packed arrays stay `double` ON PURPOSE — only the
 * operational state/forcing ABI (kdm6_step_c) went native float32 to match Fortran
 * mp37 (RWORDSIZE=4). 4D-Var adjoint/tangent precision must remain fp64 (the
 * differentiable oracle's precision); float32 gradient buffers would degrade it.
 */
int kdm6_handle_vjp_c(kdm6_handle_t* h,
                      const double* u_packed,
                      double* grad_out_packed);

/**
 * JVP — J @ v. EnKF perturbation 용. (packed arrays fp64 — see VJP note above.)
 */
int kdm6_handle_jvp_c(kdm6_handle_t* h,
                      const double* v_packed,
                      double* tangent_out_packed);

/**
 * Handle 닫기 — 자원 해제. Fortran 측이 매 step 후 *반드시* 호출해야 함.
 * NULL handle은 이미 닫힌 상태로 간주하고 KDM6_OK를 반환한다.
 */
int kdm6_handle_close_c(kdm6_handle_t* h);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // KDM6_C_API_H
