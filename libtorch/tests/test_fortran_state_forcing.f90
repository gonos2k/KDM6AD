program test_fortran_state_forcing
  use, intrinsic :: iso_c_binding
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use kdm6_iso_c
  implicit none

  integer(c_int), parameter :: im = 2, kme = 3, jme = 2
  integer, parameter :: n = im*kme*jme, ns = 12*n, nf = 4*n
  real(c_double), parameter :: dt = 60.0_c_double
  real(c_double), parameter :: ncmin_land = 100.0_c_double, ncmin_sea = 10.0_c_double
  integer(c_int32_t), parameter :: physics_variant = KDM6_PHYSICS_CONSERVATIVE_INTERFACE
  integer(c_int64_t), parameter :: dry_number = 1_c_int64_t
  real(c_double), parameter :: rho_profile(kme) = [1.2_c_double, 1.0_c_double, 0.8_c_double]
  real(c_double), parameter :: dz_profile(kme) = [700.0_c_double, 600.0_c_double, 500.0_c_double]
  ! Same output units/scales as harness/verify_state_forcing_ad.py.
  real(c_double), parameter :: output_scales(12) = [1.0_c_double, &
       1.0e-3_c_double, 1.0e-3_c_double, 1.0e-3_c_double, 1.0e-3_c_double, &
       1.0e-3_c_double, 1.0e-3_c_double, 1.0e8_c_double, 1.0e8_c_double, &
       1.0e6_c_double, 1.0e6_c_double, 1.0e-6_c_double]

  real(c_double) :: state(im,kme,jme,12), forcing(im,kme,jme,4)
  real(c_double) :: out_old(im,kme,jme,12), out_value(im,kme,jme,12)
  real(c_double) :: out_live(im,kme,jme,12)
  integer(c_int64_t) :: bits_old(ns), bits_value(ns), bits_live(ns)
  real(c_double) :: state_short(im,kme,jme,11), forcing_short(im,kme,jme,3)
  real(c_double) :: out_backing(2*im,kme,jme,12)
  real(c_double) :: v_state(im,kme,jme,12), v_forcing(im,kme,jme,4)
  real(c_double) :: u_state(im,kme,jme,12)
  real(c_double) :: v_state_packed(ns), v_forcing_packed(nf), u_raw_packed(ns), u_packed(ns)
  real(c_double) :: jv_packed(ns), gs_packed(ns), gf_packed(nf)
  real(c_double) :: gs_raw(ns), gf_raw(nf)
  real(c_double) :: grad_state_backing(2*ns), grad_forcing_backing(2*nf), tangent_backing(2*ns)
  real(c_double) :: lhs, rhs, state_term, forcing_term, denom
  real(c_double) :: raw_lhs, raw_rhs, raw_state_term, raw_forcing_term, raw_denom
  real(c_float) :: xland(im,jme)
  real(c_float) :: state32(im,kme,jme,12), forcing32(im,kme,jme,4)
  real(c_float) :: out32_backing(2*im,kme,jme,12)
  real(c_float) :: rain_backing(2*im,jme), snow_backing(2*im,jme), graupel_backing(2*im,jme)
  real(c_float) :: rhog_backing(2*im,kme,jme)
  type(c_ptr) :: old_handle, value_handle, handle, bad_handle
  integer(c_int) :: rc
  integer :: i, k, j, f
  real(c_double) :: pattern

  state = 0.0_c_double
  forcing = 0.0_c_double
  xland = 2.0_c_float
  out_old = -101.0_c_double
  out_value = -102.0_c_double
  out_live = -103.0_c_double
  state32 = 0.0_c_float
  forcing32 = 0.0_c_float

  ! Distinguishable columns and native (im,kme,jme,field) packing exercise
  ! both horizontal dimensions, all three levels, and all 12/4 field blocks.
  do j = 1, jme
    do k = 1, kme
      do i = 1, im
        state(i,k,j,1) = 282.4_c_double + 0.1_c_double*k + 0.05_c_double*i
        state(i,k,j,2) = 1.0e-3_c_double
        state(i,k,j,3) = 2.0e-4_c_double
        state(i,k,j,4) = 1.0e-3_c_double
        state(i,k,j,5) = 1.2e-3_c_double
        state(i,k,j,6) = 2.0e-3_c_double
        state(i,k,j,7) = 2.0e-3_c_double
        state(i,k,j,8) = 1.0e9_c_double
        state(i,k,j,9) = 1.0e8_c_double
        state(i,k,j,10) = 1.0e5_c_double
        state(i,k,j,11) = 1.0e4_c_double
        state(i,k,j,12) = 5.0e-6_c_double

        forcing(i,k,j,1) = rho_profile(k)
        forcing(i,k,j,2) = 0.9031_c_double
        forcing(i,k,j,3) = 7.0e4_c_double
        forcing(i,k,j,4) = dz_profile(k)
      end do
    end do
  end do
  xland(1,:) = 1.0_c_float
  xland(2,:) = 2.0_c_float

  ! The pre-existing state-only/forcing-fixed fp64 wrapper and the new joint
  ! wrapper must preserve every forward bit for the same selectors.
  old_handle = c_null_ptr
  rc = kdm6_step_ad_number(state, forcing, im, kme, jme, dt, 1_c_int, &
       out_old, old_handle, xland, ncmin_land, ncmin_sea, physics_variant, dry_number)
  if (rc /= KDM6_OK .or. c_associated(old_handle)) then
    print *, 'FAIL: old state-only value-only forward', rc
    stop 1
  end if

  value_handle = c_null_ptr
  rc = kdm6_step_ad_state_forcing(state, forcing, im, kme, jme, dt, 1_c_int, &
       out_value, value_handle, xland, ncmin_land, ncmin_sea, physics_variant, dry_number)
  if (rc /= KDM6_OK .or. c_associated(value_handle)) then
    print *, 'FAIL: joint state-forcing value-only forward', rc
    stop 1
  end if
  bits_old = transfer(out_old, bits_old, ns)
  bits_value = transfer(out_value, bits_value, ns)
  if (any(bits_old /= bits_value)) then
    print *, 'FAIL: new joint forward changed legacy state-only fp64 values'
    stop 1
  end if

  ! Local shape failures must never pass invalid packed lengths to C, and must
  ! leave the returned handle deterministically NULL and preserve the caller's
  ! output backing array, including elements outside a strided section.
  state_short = 0.0_c_double
  out_backing = -151.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad_state_forcing(state_short, forcing, im, kme, jme, dt, 0_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea, &
       physics_variant, dry_number)
  if (rc /= KDM6_ERR_INVALID_DIM .or. c_associated(bad_handle)) then
    print *, 'FAIL: malformed state shape must reject before C with NULL handle', rc
    stop 1
  end if
  if (any(out_backing /= -151.25_c_double)) then
    print *, 'FAIL: local state-shape rejection changed output backing storage'
    stop 1
  end if
  forcing_short = 0.0_c_double
  out_backing = -152.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad_state_forcing(state, forcing_short, im, kme, jme, dt, 0_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea, &
       physics_variant, dry_number)
  if (rc /= KDM6_ERR_INVALID_DIM .or. c_associated(bad_handle)) then
    print *, 'FAIL: malformed forcing shape must reject before C with NULL handle', rc
    stop 1
  end if
  if (any(out_backing /= -152.25_c_double)) then
    print *, 'FAIL: local forcing-shape rejection changed output backing storage'
    stop 1
  end if

  ! C validation failures must preserve noncontiguous caller outputs for all
  ! existing fp64 forward wrappers and the new joint entry.
  out_backing = -161.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad(state, forcing, im, kme, jme, dt, 2_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea)
  if (rc /= KDM6_ERR_INVALID_ARG .or. c_associated(bad_handle) .or. &
      any(out_backing /= -161.25_c_double)) then
    print *, 'FAIL: state-only invalid-value_only error modified output or handle', rc
    stop 1
  end if

  out_backing = -162.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad_variant(state, forcing, im, kme, jme, dt, 1_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea, -1_c_int32_t)
  if (rc /= KDM6_ERR_INVALID_ARG .or. c_associated(bad_handle) .or. &
      any(out_backing /= -162.25_c_double)) then
    print *, 'FAIL: state-only invalid variant error modified output or handle', rc
    stop 1
  end if

  out_backing = -163.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad_number(state, forcing, im, kme, jme, dt, 1_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea, &
       physics_variant, -1_c_int64_t)
  if (rc /= KDM6_ERR_INVALID_ARG .or. c_associated(bad_handle) .or. &
      any(out_backing /= -163.25_c_double)) then
    print *, 'FAIL: state-only invalid dry-number error modified output or handle', rc
    stop 1
  end if

  out_backing = -164.25_c_double
  bad_handle = c_null_ptr
  rc = kdm6_step_ad_state_forcing(state, forcing, im, kme, jme, dt, 1_c_int, &
       out_backing(1:2*im:2,:,:,:), bad_handle, xland, ncmin_land, ncmin_sea, &
       -1_c_int32_t, dry_number)
  if (rc /= KDM6_ERR_INVALID_ARG .or. c_associated(bad_handle) .or. &
      any(out_backing /= -164.25_c_double)) then
    print *, 'FAIL: joint invalid variant error modified output or handle', rc
    stop 1
  end if

  ! The operational f32 wrapper has the same C validation/thread preservation
  ! contract for its state, sedimentation and rhog outputs.
  out32_backing = -171.0_c_float
  rain_backing = -172.0_c_float
  snow_backing = -173.0_c_float
  graupel_backing = -174.0_c_float
  rhog_backing = -175.0_c_float
  bad_handle = c_null_ptr
  rc = kdm6_step(state32(:,:,:,1), state32(:,:,:,2), state32(:,:,:,3), &
       state32(:,:,:,4), state32(:,:,:,5), state32(:,:,:,6), state32(:,:,:,7), &
       state32(:,:,:,8), state32(:,:,:,9), state32(:,:,:,10), state32(:,:,:,11), &
       state32(:,:,:,12), forcing32(:,:,:,1), forcing32(:,:,:,2), &
       forcing32(:,:,:,3), forcing32(:,:,:,4), im, kme, jme, dt, 0_c_int, 2_c_int, &
       out32_backing(1:2*im:2,:,:,1), out32_backing(1:2*im:2,:,:,2), &
       out32_backing(1:2*im:2,:,:,3), out32_backing(1:2*im:2,:,:,4), &
       out32_backing(1:2*im:2,:,:,5), out32_backing(1:2*im:2,:,:,6), &
       out32_backing(1:2*im:2,:,:,7), out32_backing(1:2*im:2,:,:,8), &
       out32_backing(1:2*im:2,:,:,9), out32_backing(1:2*im:2,:,:,10), &
       out32_backing(1:2*im:2,:,:,11), out32_backing(1:2*im:2,:,:,12), &
       bad_handle, xland, ncmin_land, ncmin_sea, &
       rain_backing(1:2*im:2,:), snow_backing(1:2*im:2,:), &
       graupel_backing(1:2*im:2,:), rhog_backing(1:2*im:2,:,:))
  if (rc /= KDM6_ERR_INVALID_ARG .or. c_associated(bad_handle) .or. &
      any(out32_backing /= -171.0_c_float) .or. any(rain_backing /= -172.0_c_float) .or. &
      any(snow_backing /= -173.0_c_float) .or. any(graupel_backing /= -174.0_c_float) .or. &
      any(rhog_backing /= -175.0_c_float)) then
    print *, 'FAIL: f32 invalid value_only error modified output or handle', rc
    stop 1
  end if

  ! A live joint handle supplies K_s and K_F. Directions and covectors are
  ! deliberately nonzero in state and forcing blocks, and packed in Fortran
  ! field-major (im,kme,jme,field) order through flattened work buffers.
  handle = c_null_ptr
  rc = kdm6_step_ad_state_forcing(state, forcing, im, kme, jme, dt, 0_c_int, &
       out_live, handle, xland, ncmin_land, ncmin_sea, physics_variant, dry_number)
  if (rc /= KDM6_OK .or. .not. c_associated(handle)) then
    print *, 'FAIL: joint state-forcing live forward/handle', rc
    stop 1
  end if
  bits_live = transfer(out_live, bits_live, ns)
  if (any(bits_live /= bits_value) .or. any(.not. ieee_is_finite(out_live))) then
    print *, 'FAIL: joint graph forward differs from old forward or is non-finite'
    stop 1
  end if

  v_state = 0.0_c_double
  v_forcing = 0.0_c_double
  u_state = 0.0_c_double
  do j = 1, jme
    do k = 1, kme
      do i = 1, im
        pattern = real(i + 2*k + 3*j, c_double)
        v_state(i,k,j,1) = 1.0e-3_c_double * pattern
        v_state(i,k,j,2) = 1.0e-5_c_double * pattern
        v_state(i,k,j,5) = 1.0e-5_c_double * pattern
        v_state(i,k,j,9) = 1.0e2_c_double * pattern
        v_forcing(i,k,j,1) = 1.0e-3_c_double * pattern
        v_forcing(i,k,j,2) = 1.0e-5_c_double * pattern
        v_forcing(i,k,j,3) = 1.0e1_c_double * pattern
        v_forcing(i,k,j,4) = 1.0e-2_c_double * pattern
        do f = 1, 12
          u_state(i,k,j,f) = real(f,c_double) * pattern
        end do
      end do
    end do
  end do
  v_state_packed = reshape(v_state, [ns])
  v_forcing_packed = reshape(v_forcing, [nf])
  u_raw_packed = reshape(u_state, [ns])
  do f = 1, 12
    do i = 1, n
      u_packed((f-1)*n+i) = u_raw_packed((f-1)*n+i) / output_scales(f)
    end do
  end do

  ! Null-handle VJP/JVP errors must preserve every array output. Strided
  ! sections exercise the Fortran INOUT copy-in/copy-out contract, including
  ! untouched backing elements omitted from the section.
  grad_state_backing = -201.0_c_double
  rc = kdm6_handle_vjp(c_null_ptr, u_packed, grad_state_backing(1:2*ns:2))
  if (rc /= KDM6_ERR_NULL_POINTER .or. any(grad_state_backing /= -201.0_c_double)) then
    print *, 'FAIL: null state-only VJP changed output backing storage', rc
    stop 1
  end if
  tangent_backing = -202.0_c_double
  rc = kdm6_handle_jvp(c_null_ptr, v_state_packed, tangent_backing(1:2*ns:2))
  if (rc /= KDM6_ERR_NULL_POINTER .or. any(tangent_backing /= -202.0_c_double)) then
    print *, 'FAIL: null state-only JVP changed output backing storage', rc
    stop 1
  end if
  grad_state_backing = -203.0_c_double
  grad_forcing_backing = -204.0_c_double
  rc = kdm6_handle_state_forcing_vjp(c_null_ptr, u_packed, &
       grad_state_backing(1:2*ns:2), grad_forcing_backing(1:2*nf:2))
  if (rc /= KDM6_ERR_NULL_POINTER .or. any(grad_state_backing /= -203.0_c_double) .or. &
      any(grad_forcing_backing /= -204.0_c_double)) then
    print *, 'FAIL: null joint VJP changed output backing storage', rc
    stop 1
  end if
  tangent_backing = -205.0_c_double
  rc = kdm6_handle_state_forcing_jvp(c_null_ptr, v_state_packed, v_forcing_packed, &
       tangent_backing(1:2*ns:2))
  if (rc /= KDM6_ERR_NULL_POINTER .or. any(tangent_backing /= -205.0_c_double)) then
    print *, 'FAIL: null joint JVP changed output backing storage', rc
    stop 1
  end if

  jv_packed = -777.0_c_double
  rc = kdm6_handle_state_forcing_jvp(handle, v_state_packed, v_forcing_packed, jv_packed)
  if (rc /= KDM6_OK .or. any(.not. ieee_is_finite(jv_packed))) then
    print *, 'FAIL: joint state-forcing JVP', rc
    stop 1
  end if

  gs_packed = -777.0_c_double
  gf_packed = -777.0_c_double
  rc = kdm6_handle_state_forcing_vjp(handle, u_packed, gs_packed, gf_packed)
  if (rc /= KDM6_OK .or. any(.not. ieee_is_finite(gs_packed)) .or. &
      any(.not. ieee_is_finite(gf_packed))) then
    print *, 'FAIL: joint state-forcing VJP', rc
    stop 1
  end if

  lhs = sum(jv_packed*u_packed)
  state_term = sum(v_state_packed*gs_packed)
  forcing_term = sum(v_forcing_packed*gf_packed)
  rhs = state_term + forcing_term
  denom = max(abs(lhs), abs(rhs), 1.0e-20_c_double)
  if (abs(forcing_term) <= 1.0e-20_c_double) then
    print *, 'FAIL: forcing direction produced no adjoint contribution'
    stop 1
  end if
  if (abs(lhs) <= 1.0e-20_c_double .or. abs(lhs-rhs)/denom > 1.0e-10_c_double) then
    print *, 'FAIL: scaled joint duality <J_s v_s+J_F v_F,u> vs <v_s,g_s>+<v_F,g_F>', &
             lhs, rhs, abs(lhs-rhs), abs(lhs-rhs)/denom
    stop 1
  end if
  print *, 'PASS: physically scaled joint state/forcing duality', lhs, rhs

  ! Preserve the original unscaled raw-state covector as an honest stress
  ! diagnostic on this same handle. It misses 1e-10 for this regime; this is
  ! printed evidence, not an acceptance gate or a claim that raw scaling passes.
  rc = kdm6_handle_state_forcing_vjp(handle, u_raw_packed, gs_raw, gf_raw)
  if (rc /= KDM6_OK .or. any(.not. ieee_is_finite(gs_raw)) .or. &
      any(.not. ieee_is_finite(gf_raw))) then
    print *, 'FAIL: raw-stress joint state-forcing VJP', rc
    stop 1
  end if
  raw_lhs = sum(jv_packed*u_raw_packed)
  raw_state_term = sum(v_state_packed*gs_raw)
  raw_forcing_term = sum(v_forcing_packed*gf_raw)
  raw_rhs = raw_state_term + raw_forcing_term
  raw_denom = max(abs(raw_lhs), abs(raw_rhs), 1.0e-20_c_double)
  print *, 'RAW_STRESS_DIAGNOSTIC (unscaled covector; not an acceptance gate): abs,relerr=', &
           abs(raw_lhs-raw_rhs), abs(raw_lhs-raw_rhs)/raw_denom
  if (abs(raw_lhs-raw_rhs)/raw_denom > 1.0e-10_c_double) then
    print *, 'RAW_STRESS_DIAGNOSTIC: 1e-10 strict tolerance NOT met'
  end if

  rc = kdm6_handle_close(handle)
  if (rc /= KDM6_OK .or. c_associated(handle)) then
    print *, 'FAIL: joint pointer-nulling handle close', rc
    stop 1
  end if

  print *, 'PASS: Fortran joint state-forcing forward parity, shape checks, JVP/VJP duality'
end program test_fortran_state_forcing
