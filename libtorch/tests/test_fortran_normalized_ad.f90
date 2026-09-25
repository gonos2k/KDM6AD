program test_fortran_normalized_ad
  use, intrinsic :: iso_c_binding
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use kdm6_iso_c
  implicit none

  integer(c_int), parameter :: im = 1, kme = 4, jme = 1, n = im*kme*jme
  integer, parameter :: nf = 12
  real(c_double), parameter :: dt = 60.0_c_double
  real(c_float), target :: th(im,kme,jme), qv(im,kme,jme), qc(im,kme,jme), qr(im,kme,jme)
  real(c_float), target :: qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme)
  real(c_float), target :: nccn(im,kme,jme), nc(im,kme,jme), ni(im,kme,jme), nr(im,kme,jme), bg(im,kme,jme)
  real(c_float), target :: rho(im,kme,jme), pii(im,kme,jme), p(im,kme,jme), delz(im,kme,jme)
  real(c_float), target :: xland(im,jme)
  real(c_float), target :: out(n,nf), value_out(n,nf)
  real(c_double) :: v(nf*n), u(nf*n), jv(nf*n), jt_u(nf*n)
  real(c_double) :: lhs, rhs, denom
  type(kdm6_step_v2_args_t) :: args
  type(c_ptr), target :: handle
  integer(c_int) :: rc
  integer :: k, fld
  real(c_float), parameter :: rho_profile(kme) = [1.2_c_float, 1.0_c_float, 0.8_c_float, 0.6_c_float]
  real(c_float), parameter :: dz_profile(kme) = [700.0_c_float, 600.0_c_float, 500.0_c_float, 300.0_c_float]
  real(c_double), parameter :: pattern(kme) = [0.7_c_double, -0.4_c_double, 1.1_c_double, -0.8_c_double]

  ! Four-level mixed ice point used by the public v2 C++ gate. The state and
  ! directions travel through Fortran's ISO_C_BINDING mirror and the exact
  ! field-major packed JVP/VJP ABI. qi and ni affect DSD size/velocity.
  th = 282.4_c_float; qv = 1.0e-3_c_float; qc = 2.0e-4_c_float
  qr = 1.0e-3_c_float; qi = 1.2e-3_c_float; qs = 2.0e-3_c_float
  qg = 2.0e-3_c_float; nccn = 1.0e9_c_float; nc = 1.0e8_c_float
  ni = 1.0e5_c_float; nr = 1.0e4_c_float; bg = 5.0e-6_c_float
  pii = 0.9031_c_float; p = 7.0e4_c_float; xland = 2.0_c_float
  do k = 1, kme
    rho(1,k,1) = rho_profile(k)
    delz(1,k,1) = dz_profile(k)
  end do

  args%struct_size = int(c_sizeof(args), c_int32_t)
  args%abi_version = int(KDM6_ABI_VERSION, c_int32_t)
  args%im = int(im,c_int32_t); args%kme = int(kme,c_int32_t); args%jme = int(jme,c_int32_t)
  args%dt = dt; args%value_only = 0_c_int32_t; args%param_grad_flags = 0_c_int32_t
  args%th=c_loc(th); args%qv=c_loc(qv); args%qc=c_loc(qc); args%qr=c_loc(qr)
  args%qi=c_loc(qi); args%qs=c_loc(qs); args%qg=c_loc(qg)
  args%nccn=c_loc(nccn); args%nc=c_loc(nc); args%ni=c_loc(ni); args%nr=c_loc(nr); args%bg=c_loc(bg)
  args%rho=c_loc(rho); args%pii=c_loc(pii); args%p=c_loc(p); args%delz=c_loc(delz)
  args%th_out=c_loc(out(1,1)); args%qv_out=c_loc(out(1,2)); args%qc_out=c_loc(out(1,3)); args%qr_out=c_loc(out(1,4))
  args%qi_out=c_loc(out(1,5)); args%qs_out=c_loc(out(1,6)); args%qg_out=c_loc(out(1,7))
  args%nccn_out=c_loc(out(1,8)); args%nc_out=c_loc(out(1,9)); args%ni_out=c_loc(out(1,10))
  args%nr_out=c_loc(out(1,11)); args%bg_out=c_loc(out(1,12))
  handle = c_null_ptr; args%handle=c_loc(handle); args%xland=c_loc(xland)
  args%ncmin_land=100.0_c_double; args%ncmin_sea=10.0_c_double
  args%rain_increment=c_null_ptr; args%snow_increment=c_null_ptr
  args%graupel_increment=c_null_ptr; args%rhog_out=c_null_ptr
  args%physics_variant=KDM6_PHYSICS_CONSERVATIVE_INTERFACE

  rc = kdm6_step_v2_c(args)
  if (rc /= KDM6_OK .or. .not. c_associated(handle)) then
    print *, 'FAIL: normalized v2 value_only=0 forward/handle', rc
    stop 1
  end if

  v = 0.0_c_double; u = 0.0_c_double
  do k = 1, kme
    v(4*n+k) = real(qi(1,k,1),c_double) * 0.03_c_double * pattern(k)
    v(9*n+k) = real(ni(1,k,1),c_double) * 0.02_c_double * pattern(mod(k,kme)+1)
    do fld = 1, 7
      u((fld-1)*n+k) = real(fld*k,c_double)
    end do
  end do
  jv = -777.0_c_double; jt_u = -777.0_c_double
  rc = kdm6_handle_jvp(handle, v, jv)
  if (rc /= KDM6_OK .or. any(.not. ieee_is_finite(jv))) then
    print *, 'FAIL: normalized v2 packed JVP', rc
    stop 1
  end if
  rc = kdm6_handle_vjp(handle, u, jt_u)
  if (rc /= KDM6_OK .or. any(.not. ieee_is_finite(jt_u))) then
    print *, 'FAIL: normalized v2 packed VJP', rc
    stop 1
  end if
  lhs = sum(jv*u); rhs = sum(v*jt_u); denom = max(abs(lhs),abs(rhs),1.0e-20_c_double)
  if (abs(lhs) <= 1.0e-12_c_double) then
    print *, 'FAIL: normalized v2 qi/ni directions produced a zero response'
    stop 1
  end if
  if (abs(lhs-rhs)/denom > 2.0e-5_c_double) then
    print *, 'FAIL: normalized v2 ABI duality <Jv,u>,<v,JTu>', lhs, rhs
    stop 1
  end if

  rc = kdm6_handle_close(handle)
  if (rc /= KDM6_OK .or. c_associated(handle)) then
    print *, 'FAIL: normalized v2 pointer-nulling handle close', rc
    stop 1
  end if

  ! A separate value-only call must return no handle and exactly the same
  ! forward state. This covers the existing mp337 contract through Fortran.
  args%value_only = 1_c_int32_t
  args%th_out=c_loc(value_out(1,1)); args%qv_out=c_loc(value_out(1,2))
  args%qc_out=c_loc(value_out(1,3)); args%qr_out=c_loc(value_out(1,4))
  args%qi_out=c_loc(value_out(1,5)); args%qs_out=c_loc(value_out(1,6))
  args%qg_out=c_loc(value_out(1,7)); args%nccn_out=c_loc(value_out(1,8))
  args%nc_out=c_loc(value_out(1,9)); args%ni_out=c_loc(value_out(1,10))
  args%nr_out=c_loc(value_out(1,11)); args%bg_out=c_loc(value_out(1,12))
  handle = c_null_ptr
  rc = kdm6_step_v2_c(args)
  if (rc /= KDM6_OK .or. c_associated(handle)) then
    print *, 'FAIL: normalized v2 value_only=1 forward/NULL handle', rc
    stop 1
  end if
  if (any(out /= value_out)) then
    print *, 'FAIL: normalized v2 value-only and graph forwards differ'
    stop 1
  end if
  print *, 'PASS: Fortran normalized v2 forward, packed qi/ni JVP/VJP, duality, close, value-only parity'
end program test_fortran_normalized_ad
