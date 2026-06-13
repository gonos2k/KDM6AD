!
! kdm6_iso_c — Fortran ISO_C_BINDING wrapper for libkdm6_c.
! KIM-meso 측 microphysics dispatcher가 `use kdm6_iso_c` 후
! `call kdm6_step(...)`로 호출. 인터페이스는 C ABI(kdm6_c_api.h) 1:1 매핑.
!
! 컴파일: gfortran -c kdm6_iso_c.f90  (libkdm6_c.{so,dylib} 와 함께 링크)
!
module kdm6_iso_c
  use, intrinsic :: iso_c_binding
  implicit none
  private

  ! ── 에러 코드 (kdm6_c_api.h enum과 동기) ────────────────────────────────────
  integer(c_int), parameter, public :: KDM6_OK                  = 0
  integer(c_int), parameter, public :: KDM6_ERR_INVALID_DIM     = -1
  integer(c_int), parameter, public :: KDM6_ERR_NULL_POINTER    = -2
  integer(c_int), parameter, public :: KDM6_ERR_NOT_IMPLEMENTED = -3
  integer(c_int), parameter, public :: KDM6_ERR_HANDLE_CLOSED   = -4
  integer(c_int), parameter, public :: KDM6_ERR_VALUE_ONLY      = -5
  integer(c_int), parameter, public :: KDM6_ERR_INTERNAL        = -100

  ! ── param_grad_flags 비트마스크 ────────────────────────────────────────────
  integer(c_int), parameter, public :: KDM6_GRAD_PEAUT  = 1
  integer(c_int), parameter, public :: KDM6_GRAD_NCRK1  = 2
  integer(c_int), parameter, public :: KDM6_GRAD_NCRK2  = 4
  integer(c_int), parameter, public :: KDM6_GRAD_ECCBRK = 8
  integer(c_int), parameter, public :: KDM6_GRAD_ALL    = 15

  public :: kdm6_step, kdm6_step_ad, kdm6_handle_vjp, kdm6_handle_jvp, kdm6_handle_close

  ! ── C ABI interfaces ───────────────────────────────────────────────────────
  interface
    function kdm6_step_c( &
        th, qv, qc, qr, qi, qs, qg, &
        nccn, nc, ni, nr, bg, &
        rho, pii, p, delz, &
        im, kme, jme, dt, &
        param_grad_flags, value_only, &
        th_out, qv_out, qc_out, qr_out, &
        qi_out, qs_out, qg_out, &
        nccn_out, nc_out, ni_out, nr_out, bg_out, &
        handle, &
        xland, ncmin_land, ncmin_sea, &
        rain_increment, snow_increment, graupel_increment &
      ) bind(C, name="kdm6_step_c") result(rc)
      import :: c_int, c_double, c_float, c_ptr
      real(c_float), intent(in)  :: th(*), qv(*), qc(*), qr(*)
      real(c_float), intent(in)  :: qi(*), qs(*), qg(*)
      real(c_float), intent(in)  :: nccn(*), nc(*), ni(*), nr(*), bg(*)
      real(c_float), intent(in)  :: rho(*), pii(*), p(*), delz(*)
      integer(c_int), value       :: im, kme, jme
      real(c_double), value       :: dt
      integer(c_int), value       :: param_grad_flags, value_only
      real(c_float), intent(out) :: th_out(*), qv_out(*), qc_out(*), qr_out(*)
      real(c_float), intent(out) :: qi_out(*), qs_out(*), qg_out(*)
      real(c_float), intent(out) :: nccn_out(*), nc_out(*), ni_out(*), nr_out(*), bg_out(*)
      type(c_ptr), intent(out)    :: handle
      ! Optional appended: land/sea mask + per-regime ncmin scalars.
      ! `xland` (im, jme) float*, may be NULL → C++ falls back to scalar NCMIN.
      real(c_float), intent(in)  :: xland(*)
      real(c_double), value       :: ncmin_land, ncmin_sea
      ! Sedimentation surface increments (im, jme) [mm], Fortran column-major.
      ! Wrapper accumulates into RAINNCV/SNOWNCV/GRAUPELNCV/SR/RAIN/SNOW/GRAUPEL.
      real(c_float), intent(out) :: rain_increment(*), snow_increment(*), graupel_increment(*)
      integer(c_int)              :: rc
    end function kdm6_step_c

    ! [DA] fp64 DA adjoint forward (kdm6ad+da.md 0.1.A): same physics at
    ! float64 with a gradient graph. Packed layout = the derivative-buffer
    ! convention: state REAL(8) x(im,kme,jme,12) field order th,qv,qc,qr,qi,
    ! qs,qg,nccn,nc,ni,nr,bg; forcing REAL(8) f(im,kme,jme,4) order rho,pii,
    ! p,delz. value_only=0 -> handle for kdm6_handle_vjp_c/jvp_c (true-fp64,
    ! finite at the ice corners where the f32 graph NaNs); value_only=1 ->
    ! handle = C_NULL_PTR. Additive: the operational f32 path is untouched.
    function kdm6_step_ad_c( &
        state_in_packed, forcing_packed, &
        im, kme, jme, dt, value_only, &
        state_out_packed, handle, &
        xland, ncmin_land, ncmin_sea &
      ) bind(C, name="kdm6_step_ad_c") result(rc)
      import :: c_int, c_double, c_float, c_ptr
      real(c_double), intent(in)  :: state_in_packed(*)
      real(c_double), intent(in)  :: forcing_packed(*)
      integer(c_int), value       :: im, kme, jme
      real(c_double), value       :: dt
      integer(c_int), value       :: value_only
      real(c_double), intent(out) :: state_out_packed(*)
      type(c_ptr), intent(out)    :: handle
      real(c_float), intent(in)  :: xland(*)
      real(c_double), value       :: ncmin_land, ncmin_sea
      integer(c_int)              :: rc
    end function kdm6_step_ad_c

    function kdm6_handle_vjp_c(h, u_packed, grad_out_packed) &
        bind(C, name="kdm6_handle_vjp_c") result(rc)
      import :: c_int, c_double, c_float, c_ptr
      type(c_ptr),    value       :: h
      ! derivative ABI stays c_double (fp64 adjoint precision); only the
      ! operational state ABI (kdm6_step_c) went c_float to match mp37 RWORDSIZE=4.
      real(c_double), intent(in)  :: u_packed(*)
      real(c_double), intent(out) :: grad_out_packed(*)
      integer(c_int)              :: rc
    end function kdm6_handle_vjp_c

    function kdm6_handle_jvp_c(h, v_packed, tangent_out_packed) &
        bind(C, name="kdm6_handle_jvp_c") result(rc)
      import :: c_int, c_double, c_float, c_ptr
      type(c_ptr),    value       :: h
      real(c_double), intent(in)  :: v_packed(*)
      real(c_double), intent(out) :: tangent_out_packed(*)
      integer(c_int)              :: rc
    end function kdm6_handle_jvp_c

    function kdm6_handle_close_c(h) &
        bind(C, name="kdm6_handle_close_c") result(rc)
      import :: c_int, c_ptr
      type(c_ptr), value :: h
      integer(c_int)     :: rc
    end function kdm6_handle_close_c
  end interface

contains

  !
  ! Fortran-friendly 래퍼 — assumed-shape array를 받아 contiguous 가정 후
  ! C ABI에 위임. KIM-meso 측은 (ims:ime, kms:kme, jms:jme) 배열을 그대로 전달.
  !
  function kdm6_step( &
      th, qv, qc, qr, qi, qs, qg, &
      nccn, nc, ni, nr, bg, &
      rho, pii, p, delz, &
      im, kme, jme, dt, &
      param_grad_flags, value_only, &
      th_out, qv_out, qc_out, qr_out, &
      qi_out, qs_out, qg_out, &
      nccn_out, nc_out, ni_out, nr_out, bg_out, &
      handle, &
      xland, ncmin_land, ncmin_sea, &
      rain_increment, snow_increment, graupel_increment &
    ) result(rc)
    real(c_float), intent(in),  contiguous :: th(:,:,:), qv(:,:,:), qc(:,:,:), qr(:,:,:)
    real(c_float), intent(in),  contiguous :: qi(:,:,:), qs(:,:,:), qg(:,:,:)
    real(c_float), intent(in),  contiguous :: nccn(:,:,:), nc(:,:,:), ni(:,:,:), nr(:,:,:), bg(:,:,:)
    real(c_float), intent(in),  contiguous :: rho(:,:,:), pii(:,:,:), p(:,:,:), delz(:,:,:)
    integer(c_int), intent(in)              :: im, kme, jme
    real(c_double), intent(in)              :: dt
    integer(c_int), intent(in)              :: param_grad_flags, value_only
    real(c_float), intent(out), contiguous :: th_out(:,:,:), qv_out(:,:,:), qc_out(:,:,:), qr_out(:,:,:)
    real(c_float), intent(out), contiguous :: qi_out(:,:,:), qs_out(:,:,:), qg_out(:,:,:)
    real(c_float), intent(out), contiguous :: nccn_out(:,:,:), nc_out(:,:,:), ni_out(:,:,:), nr_out(:,:,:)
    real(c_float), intent(out), contiguous :: bg_out(:,:,:)
    type(c_ptr),    intent(out)             :: handle
    ! Land/sea mask (im, jme) + per-regime ncmin scalars.
    real(c_float), intent(in),  contiguous :: xland(:,:)
    real(c_double), intent(in)              :: ncmin_land, ncmin_sea
    ! Sedimentation surface increments (im, jme) [mm] — caller-allocated.
    real(c_float), intent(out), contiguous :: rain_increment(:,:)
    real(c_float), intent(out), contiguous :: snow_increment(:,:)
    real(c_float), intent(out), contiguous :: graupel_increment(:,:)
    integer(c_int)                          :: rc

    rc = kdm6_step_c( &
      th, qv, qc, qr, qi, qs, qg, &
      nccn, nc, ni, nr, bg, &
      rho, pii, p, delz, &
      im, kme, jme, dt, &
      param_grad_flags, value_only, &
      th_out, qv_out, qc_out, qr_out, &
      qi_out, qs_out, qg_out, &
      nccn_out, nc_out, ni_out, nr_out, bg_out, &
      handle, &
      xland, real(ncmin_land, c_double), real(ncmin_sea, c_double), &
      rain_increment, snow_increment, graupel_increment)
  end function kdm6_step

  ! [DA] fp64 DA adjoint forward — Fortran-friendly wrapper over kdm6_step_ad_c.
  ! state(im,kme,jme,12) field order th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg;
  ! forcing(im,kme,jme,4) order rho,pii,p,delz. value_only=0 -> live handle
  ! for kdm6_handle_vjp/jvp (true-fp64 adjoints); value_only=1 -> C_NULL_PTR.
  ! xland is REQUIRED here (hosts always have XLAND); the C ABI's NULL-xland
  ! default path is reachable from C callers only (Codex review finding 3).
  function kdm6_step_ad( &
      state_in, forcing, &
      im, kme, jme, dt, value_only, &
      state_out, handle, &
      xland, ncmin_land, ncmin_sea &
    ) result(rc)
    real(c_double), intent(in),  contiguous :: state_in(:,:,:,:)
    real(c_double), intent(in),  contiguous :: forcing(:,:,:,:)
    integer(c_int), intent(in)              :: im, kme, jme
    real(c_double), intent(in)              :: dt
    integer(c_int), intent(in)              :: value_only
    real(c_double), intent(out), contiguous :: state_out(:,:,:,:)
    type(c_ptr),    intent(out)             :: handle
    real(c_float),  intent(in),  contiguous :: xland(:,:)
    real(c_double), intent(in)              :: ncmin_land, ncmin_sea
    integer(c_int)                          :: rc
    rc = kdm6_step_ad_c(state_in, forcing, im, kme, jme, dt, value_only, &
                        state_out, handle, xland, ncmin_land, ncmin_sea)
  end function kdm6_step_ad

  function kdm6_handle_vjp(h, u_packed, grad_out_packed) result(rc)
    type(c_ptr),    intent(in)              :: h
    real(c_double), intent(in),  contiguous :: u_packed(:)
    real(c_double), intent(out), contiguous :: grad_out_packed(:)
    integer(c_int)                          :: rc
    rc = kdm6_handle_vjp_c(h, u_packed, grad_out_packed)
  end function kdm6_handle_vjp

  function kdm6_handle_jvp(h, v_packed, tangent_out_packed) result(rc)
    type(c_ptr),    intent(in)              :: h
    real(c_double), intent(in),  contiguous :: v_packed(:)
    real(c_double), intent(out), contiguous :: tangent_out_packed(:)
    integer(c_int)                          :: rc
    rc = kdm6_handle_jvp_c(h, v_packed, tangent_out_packed)
  end function kdm6_handle_jvp

  function kdm6_handle_close(h) result(rc)
    type(c_ptr), intent(in) :: h
    integer(c_int)          :: rc
    rc = kdm6_handle_close_c(h)
  end function kdm6_handle_close

end module kdm6_iso_c
