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
 * 입력 state/forcing은 Fortran-allocated double*(im, kme, jme).
 * 출력 state는 caller가 *미리 할당*한 double*(im, kme, jme)에 결과 복사.
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
    const double* th, const double* qv, const double* qc, const double* qr,
    const double* qi, const double* qs, const double* qg,
    const double* nccn, const double* nc, const double* ni, const double* nr,
    const double* bg,
    /* in: 4 forcing */
    const double* rho, const double* pii, const double* p, const double* delz,
    /* in: dimensions, dt, flags */
    int im, int kme, int jme, double dt,
    int param_grad_flags, int value_only,
    /* out: 12 prognostic */
    double* th_out, double* qv_out, double* qc_out, double* qr_out,
    double* qi_out, double* qs_out, double* qg_out,
    double* nccn_out, double* nc_out, double* ni_out, double* nr_out,
    double* bg_out,
    /* out: opaque handle */
    kdm6_handle_t** handle
);

/**
 * VJP — J^T @ u. 4D-Var adjoint 용.
 *
 * `u_packed`는 12 필드 × (im*jme*kme) double의 *연결된* 배열.
 * `grad_out_packed`도 동일 layout, caller-allocated.
 *
 * @return KDM6_OK 또는 KDM6_ERR_VALUE_ONLY / HANDLE_CLOSED / NOT_IMPLEMENTED.
 */
int kdm6_handle_vjp_c(kdm6_handle_t* h,
                      const double* u_packed,
                      double* grad_out_packed);

/**
 * JVP — J @ v. EnKF perturbation 용.
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
