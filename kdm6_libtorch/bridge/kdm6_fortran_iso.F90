! ──────────────────────────────────────────────────────────────────────────────
! KDM6 libtorch — Fortran ISO_C_BINDING 인터페이스
!
! KIM-meso 슬롯 47 호출용. forward(슬롯 37) 직후 동일 state로 호출하여
! derivative 정보를 산출.
!
! 사용 예:
!   USE kdm6_libtorch
!   INTEGER(C_INT) :: rc
!   TYPE(C_PTR)    :: handle
!   rc = kdm6_step(th, qv, qc, ..., bg, &
!                  rho, pii, p, delz, &
!                  im, kme, jme, dt, &
!                  param_grad_flags, value_only, &
!                  th_out, ..., bg_out, &
!                  handle)
!   IF (rc /= KDM6_OK) CALL handle_error(rc)
!   ! ... 이후 vjp/jvp/close ...
! ──────────────────────────────────────────────────────────────────────────────

MODULE kdm6_libtorch
  USE, INTRINSIC :: ISO_C_BINDING
  IMPLICIT NONE

  ! 에러 코드 (kdm6_c_api.h와 정합)
  INTEGER(C_INT), PARAMETER :: KDM6_OK                  =   0
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_INVALID_DIM     =  -1
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_NULL_POINTER    =  -2
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_NOT_IMPLEMENTED =  -3
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_HANDLE_CLOSED   =  -4
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_VALUE_ONLY      =  -5
  INTEGER(C_INT), PARAMETER :: KDM6_ERR_INTERNAL        = -100

  ! Param grad 비트마스크
  INTEGER(C_INT), PARAMETER :: KDM6_PARAM_PEAUT  = 1
  INTEGER(C_INT), PARAMETER :: KDM6_PARAM_NCRK1  = 2
  INTEGER(C_INT), PARAMETER :: KDM6_PARAM_NCRK2  = 4
  INTEGER(C_INT), PARAMETER :: KDM6_PARAM_ECCBRK = 8
  INTEGER(C_INT), PARAMETER :: KDM6_PARAM_ALL    = 15

  INTERFACE
    FUNCTION kdm6_step_c(th, qv, qc, qr, qi, qs, qg, &
                         nccn, nc, ni, nr, bg, &
                         rho, pii, p, delz, &
                         im, kme, jme, dt, &
                         param_grad_flags, value_only, &
                         th_out, qv_out, qc_out, qr_out, &
                         qi_out, qs_out, qg_out, &
                         nccn_out, nc_out, ni_out, nr_out, bg_out, &
                         handle) BIND(C, name="kdm6_step_c") RESULT(rc)
      USE, INTRINSIC :: ISO_C_BINDING
      INTEGER(C_INT)                                 :: rc
      ! 12 prognostic state inputs
      REAL(C_DOUBLE), DIMENSION(*), INTENT(IN)       :: th, qv, qc, qr, qi, qs, qg
      REAL(C_DOUBLE), DIMENSION(*), INTENT(IN)       :: nccn, nc, ni, nr, bg
      ! 4 forcing inputs
      REAL(C_DOUBLE), DIMENSION(*), INTENT(IN)       :: rho, pii, p, delz
      ! dimensions, dt, flags
      INTEGER(C_INT), VALUE                          :: im, kme, jme
      REAL(C_DOUBLE), VALUE                          :: dt
      INTEGER(C_INT), VALUE                          :: param_grad_flags, value_only
      ! 12 prognostic state outputs (caller-allocated)
      REAL(C_DOUBLE), DIMENSION(*), INTENT(INOUT)    :: th_out, qv_out, qc_out, qr_out
      REAL(C_DOUBLE), DIMENSION(*), INTENT(INOUT)    :: qi_out, qs_out, qg_out
      REAL(C_DOUBLE), DIMENSION(*), INTENT(INOUT)    :: nccn_out, nc_out, ni_out, nr_out, bg_out
      ! opaque handle
      TYPE(C_PTR), INTENT(OUT)                       :: handle
    END FUNCTION kdm6_step_c

    FUNCTION kdm6_handle_vjp_c(h, u_packed, grad_out_packed) &
             BIND(C, name="kdm6_handle_vjp_c") RESULT(rc)
      USE, INTRINSIC :: ISO_C_BINDING
      INTEGER(C_INT)                              :: rc
      TYPE(C_PTR), VALUE                          :: h
      REAL(C_DOUBLE), DIMENSION(*), INTENT(IN)    :: u_packed
      REAL(C_DOUBLE), DIMENSION(*), INTENT(INOUT) :: grad_out_packed
    END FUNCTION kdm6_handle_vjp_c

    FUNCTION kdm6_handle_jvp_c(h, v_packed, tangent_out_packed) &
             BIND(C, name="kdm6_handle_jvp_c") RESULT(rc)
      USE, INTRINSIC :: ISO_C_BINDING
      INTEGER(C_INT)                              :: rc
      TYPE(C_PTR), VALUE                          :: h
      REAL(C_DOUBLE), DIMENSION(*), INTENT(IN)    :: v_packed
      REAL(C_DOUBLE), DIMENSION(*), INTENT(INOUT) :: tangent_out_packed
    END FUNCTION kdm6_handle_jvp_c

    FUNCTION kdm6_handle_close_c(h) BIND(C, name="kdm6_handle_close_c") RESULT(rc)
      USE, INTRINSIC :: ISO_C_BINDING
      INTEGER(C_INT)     :: rc
      TYPE(C_PTR), VALUE :: h
    END FUNCTION kdm6_handle_close_c
  END INTERFACE

CONTAINS

  SUBROUTINE kdm6_close(handle, rc)
    TYPE(C_PTR), INTENT(INOUT) :: handle
    INTEGER(C_INT), INTENT(OUT) :: rc

    rc = kdm6_handle_close_c(handle)
    IF (rc == KDM6_OK) THEN
      handle = C_NULL_PTR
    END IF
  END SUBROUTINE kdm6_close

END MODULE kdm6_libtorch
