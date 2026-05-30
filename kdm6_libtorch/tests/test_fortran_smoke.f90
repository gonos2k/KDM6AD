!
! Fortran end-to-end smoke — `use kdm6_iso_c` → kdm6_step → libkdm6_c.{so,dylib}
! → kdm6::kdm6_step → kdm6_fn → kdm62d_step → microphysics.
!
! Task #99 회귀: KIM-meso wrapper가 호출할 정확한 경로(Fortran ISO_C_BINDING)를
! exercise. 단일 (im, kme, jme) = (1, 1, 1) warm-phase active 셀에서
! microphysics가 실제 실행되어 qc/qr이 변화함을 검증.
!
program test_fortran_smoke
  use, intrinsic :: iso_c_binding
  use kdm6_iso_c
  implicit none

  integer(c_int), parameter :: im = 1, kme = 1, jme = 1
  real(c_double), parameter :: dt = 60.0_c_double

  real(c_double), allocatable, dimension(:,:,:) :: th, qv, qc, qr, qi, qs, qg
  real(c_double), allocatable, dimension(:,:,:) :: nccn, nc, ni, nr, bg
  real(c_double), allocatable, dimension(:,:,:) :: rho, pii, p, delz
  real(c_double), allocatable, dimension(:,:,:) :: th_o, qv_o, qc_o, qr_o, qi_o, qs_o, qg_o
  real(c_double), allocatable, dimension(:,:,:) :: nccn_o, nc_o, ni_o, nr_o, bg_o
  ! Phase 3 ABI extension — land/sea mask + per-regime ncmin scalars.
  real(c_double), allocatable, dimension(:,:) :: xland
  ! Phase 4 ABI extension — sedimentation surface increments (im, jme) [mm].
  real(c_double), allocatable, dimension(:,:) :: rain_inc, snow_inc, graupel_inc

  type(c_ptr) :: handle
  integer(c_int) :: rc

  print *, "kdm6 Fortran ISO_C_BINDING smoke test"

  ! ── Allocate ────────────────────────────────────────────────────────────────
  allocate(th(im, kme, jme), qv(im, kme, jme), qc(im, kme, jme), qr(im, kme, jme))
  allocate(qi(im, kme, jme), qs(im, kme, jme), qg(im, kme, jme))
  allocate(nccn(im, kme, jme), nc(im, kme, jme), ni(im, kme, jme), nr(im, kme, jme))
  allocate(bg(im, kme, jme))
  allocate(rho(im, kme, jme), pii(im, kme, jme), p(im, kme, jme), delz(im, kme, jme))
  allocate(th_o(im, kme, jme), qv_o(im, kme, jme), qc_o(im, kme, jme), qr_o(im, kme, jme))
  allocate(qi_o(im, kme, jme), qs_o(im, kme, jme), qg_o(im, kme, jme))
  allocate(nccn_o(im, kme, jme), nc_o(im, kme, jme), ni_o(im, kme, jme), nr_o(im, kme, jme))
  allocate(bg_o(im, kme, jme))
  allocate(xland(im, jme))
  allocate(rain_inc(im, jme), snow_inc(im, jme), graupel_inc(im, jme))

  ! ── Warm-phase active cell (test_c_abi.cpp와 동일 입력) ───────────────────
  th   = 285.0_c_double / 1.1_c_double   ! T=285K, π=1.1
  qv   = 6.5e-3_c_double                 ! sub-saturated
  qc   = 5.0e-4_c_double
  qr   = 1.0e-4_c_double
  qi   = 0.0_c_double
  qs   = 0.0_c_double
  qg   = 0.0_c_double
  nccn = 0.0_c_double
  nc   = 1.0e8_c_double
  ni   = 0.0_c_double
  nr   = 1.0e5_c_double
  bg   = 0.0_c_double

  rho  = 1.0_c_double
  pii  = 1.1_c_double
  p    = 8.0e4_c_double
  delz = 550.0_c_double

  xland = 2.0_c_double                       ! all-sea regime (matches pre-extension hardcode)

  ! ── Call kdm6_step via ISO_C_BINDING module ────────────────────────────────
  rc = kdm6_step(th, qv, qc, qr, qi, qs, qg, &
                 nccn, nc, ni, nr, bg, &
                 rho, pii, p, delz, &
                 im, kme, jme, dt, &
                 0_c_int,        & ! param_grad_flags = 0 (frozen)
                 1_c_int,        & ! value_only = 1
                 th_o, qv_o, qc_o, qr_o, qi_o, qs_o, qg_o, &
                 nccn_o, nc_o, ni_o, nr_o, bg_o, &
                 handle, &
                 xland, 100.0_c_double, 10.0_c_double, & ! ncmin_land, ncmin_sea
                 rain_inc, snow_inc, graupel_inc)        ! Phase 4 precip incs

  if (rc /= KDM6_OK) then
     print *, "FAIL: kdm6_step returned ", rc
     stop 1
  end if
  print *, "  PASS: kdm6_step rc=KDM6_OK"

  ! ── Output integrity ────────────────────────────────────────────────────────
  if (any(.not. (qv_o == qv_o)) .or. any(.not. (qc_o == qc_o))) then
     print *, "FAIL: NaN in output"
     stop 1
  end if
  if (any(qv_o < 0.0_c_double) .or. any(qc_o < 0.0_c_double) .or. any(qr_o < 0.0_c_double)) then
     print *, "FAIL: negative water mixing ratio"
     stop 1
  end if
  print *, "  PASS: output finite + non-negative"

  ! ── Microphysics actually ran (state evolved) ──────────────────────────────
  if (abs(qc_o(1,1,1) - qc(1,1,1)) < 1.0e-12_c_double .and. &
      abs(qr_o(1,1,1) - qr(1,1,1)) < 1.0e-12_c_double) then
     print *, "FAIL: state unchanged (microphysics did not run)"
     stop 1
  end if
  print *, "  PASS: state evolved (qc/qr changed)"
  print '(a, es12.5, a, es12.5)', "    qc: ", qc(1,1,1), " -> ", qc_o(1,1,1)
  print '(a, es12.5, a, es12.5)', "    qr: ", qr(1,1,1), " -> ", qr_o(1,1,1)

  ! ── Handle lifecycle ────────────────────────────────────────────────────────
  rc = kdm6_handle_close(handle)
  if (rc /= KDM6_OK) then
     print *, "FAIL: kdm6_handle_close returned ", rc
     stop 1
  end if
  print *, "  PASS: kdm6_handle_close rc=KDM6_OK"

  print *, "All Fortran ISO_C_BINDING tests passed."
end program test_fortran_smoke
