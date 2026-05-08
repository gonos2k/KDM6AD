






module kdm6_iso_c
  use, intrinsic :: iso_c_binding
  implicit none
  private

  
  integer(c_int), parameter, public :: KDM6_OK                  = 0
  integer(c_int), parameter, public :: KDM6_ERR_INVALID_DIM     = -1
  integer(c_int), parameter, public :: KDM6_ERR_NULL_POINTER    = -2
  integer(c_int), parameter, public :: KDM6_ERR_NOT_IMPLEMENTED = -3
  integer(c_int), parameter, public :: KDM6_ERR_HANDLE_CLOSED   = -4
  integer(c_int), parameter, public :: KDM6_ERR_VALUE_ONLY      = -5
  integer(c_int), parameter, public :: KDM6_ERR_INTERNAL        = -100

  
  integer(c_int), parameter, public :: KDM6_GRAD_PEAUT  = 1
  integer(c_int), parameter, public :: KDM6_GRAD_NCRK1  = 2
  integer(c_int), parameter, public :: KDM6_GRAD_NCRK2  = 4
  integer(c_int), parameter, public :: KDM6_GRAD_ECCBRK = 8
  integer(c_int), parameter, public :: KDM6_GRAD_ALL    = 15

  public :: kdm6_step, kdm6_handle_vjp, kdm6_handle_jvp, kdm6_handle_close

  
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
        handle &
      ) bind(C, name="kdm6_step_c") result(rc)
      import :: c_int, c_double, c_ptr
      real(c_double), intent(in)  :: th(*), qv(*), qc(*), qr(*)
      real(c_double), intent(in)  :: qi(*), qs(*), qg(*)
      real(c_double), intent(in)  :: nccn(*), nc(*), ni(*), nr(*), bg(*)
      real(c_double), intent(in)  :: rho(*), pii(*), p(*), delz(*)
      integer(c_int), value       :: im, kme, jme
      real(c_double), value       :: dt
      integer(c_int), value       :: param_grad_flags, value_only
      real(c_double), intent(out) :: th_out(*), qv_out(*), qc_out(*), qr_out(*)
      real(c_double), intent(out) :: qi_out(*), qs_out(*), qg_out(*)
      real(c_double), intent(out) :: nccn_out(*), nc_out(*), ni_out(*), nr_out(*), bg_out(*)
      type(c_ptr), intent(out)    :: handle
      integer(c_int)              :: rc
    end function kdm6_step_c

    function kdm6_handle_vjp_c(h, u_packed, grad_out_packed) &
        bind(C, name="kdm6_handle_vjp_c") result(rc)
      import :: c_int, c_double, c_ptr
      type(c_ptr),    value       :: h
      real(c_double), intent(in)  :: u_packed(*)
      real(c_double), intent(out) :: grad_out_packed(*)
      integer(c_int)              :: rc
    end function kdm6_handle_vjp_c

    function kdm6_handle_jvp_c(h, v_packed, tangent_out_packed) &
        bind(C, name="kdm6_handle_jvp_c") result(rc)
      import :: c_int, c_double, c_ptr
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

  
  
  
  
  function kdm6_step( &
      th, qv, qc, qr, qi, qs, qg, &
      nccn, nc, ni, nr, bg, &
      rho, pii, p, delz, &
      im, kme, jme, dt, &
      param_grad_flags, value_only, &
      th_out, qv_out, qc_out, qr_out, &
      qi_out, qs_out, qg_out, &
      nccn_out, nc_out, ni_out, nr_out, bg_out, &
      handle &
    ) result(rc)
    real(c_double), intent(in),  contiguous :: th(:,:,:), qv(:,:,:), qc(:,:,:), qr(:,:,:)
    real(c_double), intent(in),  contiguous :: qi(:,:,:), qs(:,:,:), qg(:,:,:)
    real(c_double), intent(in),  contiguous :: nccn(:,:,:), nc(:,:,:), ni(:,:,:), nr(:,:,:), bg(:,:,:)
    real(c_double), intent(in),  contiguous :: rho(:,:,:), pii(:,:,:), p(:,:,:), delz(:,:,:)
    integer(c_int), intent(in)              :: im, kme, jme
    real(c_double), intent(in)              :: dt
    integer(c_int), intent(in)              :: param_grad_flags, value_only
    real(c_double), intent(out), contiguous :: th_out(:,:,:), qv_out(:,:,:), qc_out(:,:,:), qr_out(:,:,:)
    real(c_double), intent(out), contiguous :: qi_out(:,:,:), qs_out(:,:,:), qg_out(:,:,:)
    real(c_double), intent(out), contiguous :: nccn_out(:,:,:), nc_out(:,:,:), ni_out(:,:,:), nr_out(:,:,:)
    real(c_double), intent(out), contiguous :: bg_out(:,:,:)
    type(c_ptr),    intent(out)             :: handle
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
      handle)
  end function kdm6_step

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


