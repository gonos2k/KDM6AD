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
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use kdm6_iso_c
  implicit none

  integer(c_int), parameter :: im = 1, kme = 1, jme = 1
  real(c_double), parameter :: dt = 60.0_c_double

  ! native float32 operational ABI (arrays c_float; dt/ncmin scalars stay c_double)
  real(c_float), allocatable, dimension(:,:,:) :: th, qv, qc, qr, qi, qs, qg
  real(c_float), allocatable, dimension(:,:,:) :: nccn, nc, ni, nr, bg
  real(c_float), allocatable, dimension(:,:,:) :: rho, pii, p, delz
  real(c_float), allocatable, dimension(:,:,:) :: th_o, qv_o, qc_o, qr_o, qi_o, qs_o, qg_o
  real(c_float), allocatable, dimension(:,:,:) :: nccn_o, nc_o, ni_o, nr_o, bg_o
  ! Phase 3 ABI extension — land/sea mask + per-regime ncmin scalars.
  real(c_float), allocatable, dimension(:,:) :: xland
  ! Phase 4 ABI extension — sedimentation surface increments (im, jme) [mm].
  real(c_float), allocatable, dimension(:,:) :: rain_inc, snow_inc, graupel_inc
  ! Graupel density diagnostic (im, kme, jme) → WRF diag_rhog/RHOPO3D.
  real(c_float), allocatable, dimension(:,:,:) :: rhog_o

  type(c_ptr) :: handle
  integer(c_int) :: rc

  print *, "kdm6 Fortran ISO_C_BINDING smoke test"

  ! ABI error-code sync guard (PR1-A): kdm6_iso_c.f90 hand-mirrors the C enum,
  ! so a new C error code that is not mirrored here would leave the host unable
  ! to name it. Pin the newest one against its C value.
  if (KDM6_ERR_THREAD_CONFIG /= -7_c_int) then
     print *, "FAIL: Fortran/C ABI KDM6_ERR_THREAD_CONFIG mismatch (want -7, got ", &
              KDM6_ERR_THREAD_CONFIG, ")"
     stop 1
  end if
  print *, "  PASS: KDM6_ERR_THREAD_CONFIG synced (-7)"

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
  allocate(rhog_o(im, kme, jme))

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
                 rain_inc, snow_inc, graupel_inc, &      ! Phase 4 precip incs
                 rhog_o)                                 ! graupel density → diag_rhog

  if (rc /= KDM6_OK) then
     print *, "FAIL: kdm6_step returned ", rc
     stop 1
  end if
  print *, "  PASS: kdm6_step rc=KDM6_OK"

  ! ── Output integrity ────────────────────────────────────────────────────────
  if (any(.not. ieee_is_finite(qv_o)) .or. any(.not. ieee_is_finite(qc_o))) then
     print *, "FAIL: non-finite (NaN/Inf) in output"
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

  ! ── [DA] fp64 adjoint-forward wrapper: kdm6_step_ad + kdm6_handle_vjp ─────────
  ! Single-cell MECHANICS of the 4D assumed-shape `contiguous` Fortran wrapper:
  ! rank/assumed-shape pass-through, value_only=0 graph build, live handle,
  ! VJP call + finite + nonzero gradient, handle lifecycle. (Single cell does NOT
  ! prove the (im,kme,jme) packed-layout offset — that is the tile_test below, and
  ! C++ test_c_abi_vjp_packed_layout_nontrivial_tile covers the C ABI side.)
  ! packed state(im,kme,jme,12) / forcing(im,kme,jme,4) REAL(8).
  ad_test: block
    real(c_double), allocatable :: state_in(:,:,:,:), state_out(:,:,:,:)
    real(c_double), allocatable :: forcing(:,:,:,:)
    real(c_double), allocatable :: u_packed(:), grad_out_packed(:)
    type(c_ptr) :: ad_handle
    logical :: any_nonzero
    integer :: i

    allocate(state_in(im, kme, jme, 12), state_out(im, kme, jme, 12))
    allocate(forcing(im, kme, jme, 4))
    allocate(u_packed(im*kme*jme*12), grad_out_packed(im*kme*jme*12))

    ! same warm-phase active cell (field order th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg)
    state_in(:,:,:, 1) = 285.0_c_double / 1.1_c_double   ! th
    state_in(:,:,:, 2) = 6.5e-3_c_double                 ! qv
    state_in(:,:,:, 3) = 5.0e-4_c_double                 ! qc
    state_in(:,:,:, 4) = 1.0e-4_c_double                 ! qr
    state_in(:,:,:, 5) = 0.0_c_double                    ! qi
    state_in(:,:,:, 6) = 0.0_c_double                    ! qs
    state_in(:,:,:, 7) = 0.0_c_double                    ! qg
    state_in(:,:,:, 8) = 0.0_c_double                    ! nccn
    state_in(:,:,:, 9) = 1.0e8_c_double                  ! nc
    state_in(:,:,:,10) = 0.0_c_double                    ! ni
    state_in(:,:,:,11) = 1.0e5_c_double                  ! nr
    state_in(:,:,:,12) = 0.0_c_double                    ! bg

    forcing(:,:,:, 1) = 1.0_c_double                     ! rho
    forcing(:,:,:, 2) = 1.1_c_double                     ! pii
    forcing(:,:,:, 3) = 8.0e4_c_double                   ! p
    forcing(:,:,:, 4) = 550.0_c_double                   ! delz

    state_out       = -777.0_c_double
    grad_out_packed = -777.0_c_double

    ! value_only=0 -> fp64 graph handle for the adjoint (xland reused from above)
    rc = kdm6_step_ad(state_in, forcing, im, kme, jme, dt, 0_c_int, &
                      state_out, ad_handle, xland, 100.0_c_double, 10.0_c_double)
    if (rc /= KDM6_OK) then
       print *, "FAIL: kdm6_step_ad returned ", rc
       stop 1
    end if
    if (.not. c_associated(ad_handle)) then
       print *, "FAIL: kdm6_step_ad value_only=0 returned NULL handle"
       stop 1
    end if
    if (any(state_out == -777.0_c_double) .or. any(.not. ieee_is_finite(state_out))) then
       print *, "FAIL: kdm6_step_ad output not fully written / non-finite"
       stop 1
    end if
    print *, "  PASS: kdm6_step_ad rc=KDM6_OK, live handle, output finite"

    ! FIELD-semantic check pins the absolute packed FIELD offset (the layout dim the
    ! tile support-confinement and standalone tests do NOT pin — a field scramble
    ! consistent across shapes slips through those). This warm cell (T~285K) forms
    ! NO ice, so packed output ICE fields qi(5)/qs(6)/qg(7) must stay ~0 while qc(3)
    ! evolves; a wrong field offset misplaces the warm signature and FAILS here.
    if (abs(state_out(1,1,1,5)) > 1.0e-12_c_double .or. &
        abs(state_out(1,1,1,6)) > 1.0e-12_c_double .or. &
        abs(state_out(1,1,1,7)) > 1.0e-12_c_double) then
       print *, "FAIL: warm-cell packed output has spurious ice (field offset?) qi/qs/qg=", &
                state_out(1,1,1,5), state_out(1,1,1,6), state_out(1,1,1,7)
       stop 1
    end if
    if (abs(state_out(1,1,1,3) - state_in(1,1,1,3)) <= 1.0e-12_c_double) then
       print *, "FAIL: warm-cell qc (field 3) did not evolve in packed path (field offset?)"
       stop 1
    end if
    print *, "  PASS: packed warm-cell field semantics (no ice, qc evolved) — field offset pinned"

    ! VJP through the live handle: deterministic covector u -> grad_out (fp64).
    do i = 1, size(u_packed)
       u_packed(i) = 1.0_c_double + 0.25_c_double * real(mod(i-1, 7), c_double)
    end do
    rc = kdm6_handle_vjp(ad_handle, u_packed, grad_out_packed)
    if (rc /= KDM6_OK) then
       print *, "FAIL: kdm6_handle_vjp returned ", rc
       stop 1
    end if
    any_nonzero = .false.
    do i = 1, size(grad_out_packed)
       if (grad_out_packed(i) == -777.0_c_double) then
          print *, "FAIL: kdm6_handle_vjp left grad_out unwritten at index ", i
          stop 1
       end if
       if (.not. ieee_is_finite(grad_out_packed(i))) then           ! fp64: must be finite (NaN+Inf)
          print *, "FAIL: non-finite (NaN/Inf) in fp64 VJP gradient at index ", i
          stop 1
       end if
       if (grad_out_packed(i) /= 0.0_c_double) any_nonzero = .true.
    end do
    if (.not. any_nonzero) then
       print *, "FAIL: VJP gradient identically zero (no sensitivity)"
       stop 1
    end if
    print *, "  PASS: kdm6_handle_vjp finite + nonzero gradient"

    rc = kdm6_handle_close(ad_handle)
    if (rc /= KDM6_OK) then
       print *, "FAIL: kdm6_handle_close(ad_handle) returned ", rc
       stop 1
    end if
    print *, "  PASS: kdm6_step_ad handle lifecycle closed"

    deallocate(state_in, state_out, forcing, u_packed, grad_out_packed)
  end block ad_test

  ! ── [DA] fp64 nontrivial-tile VJP support-confinement (Codex review finding 3) ─
  ! kdm6 columns evolve independently (no HORIZONTAL coupling; vertical k-levels DO
  ! couple via sedimentation), so a VJP covector on ONE Fortran cell (i0,k0,j0) must
  ! produce gradient support confined to the SAME (i0,j0) horizontal column. This
  ! exercises the 4D Fortran wrapper's assumed-shape (im,kme,jme,12) -> packed(*)
  ! path on im=2,kme=2,jme=2: a wrong (im,kme,jme) AXIS layout lands the support in
  ! the wrong column and FAILS here.
  ! SCOPE: this catches (im,kme,jme) AXIS-permutation, NOT full per-(field,k) offset
  ! correctness — the field/k offset is the C ABI reshape (covered by C++
  ! test_c_abi_vjp_packed_layout_nontrivial_tile); the Fortran wrapper only passes
  ! the contiguous buffer through. fp64 path => grads must be ALL finite (a NaN OR
  ! Inf here is a contract violation and FAILS via ieee_is_finite, it is NOT skipped).
  tile_test: block
    ! DISTINCT extents (im,kme,jme)=(2,3,4) so NO axis permutation is a tile
    ! symmetry — an im<->jme (or any axis) swap moves support out of column
    ! (i0,j0) and FAILS. (A symmetric 2x2x2 tile with i0==j0 hides an im<->jme
    ! swap: the seed cell maps to itself. Codex stop-review.)
    integer, parameter :: ti = 2, tk = 3, tj = 4, nfld = 12
    integer, parameter :: nn = ti * tk * tj
    integer, parameter :: i0 = 2, k0 = 2, j0 = 3     ! 1-based; i0/=j0 (asymmetric); field qv = 2
    real(c_double), allocatable :: s_in(:,:,:,:), s_out(:,:,:,:), f_in(:,:,:,:)
    real(c_double), allocatable :: u_pk(:), g_pk(:)
    real(c_float),  allocatable :: xland2(:,:)
    type(c_ptr) :: th_handle
    integer :: i, k, j, fld, cell0, pidx
    real(c_double) :: colf
    logical :: any_in_col

    allocate(s_in(ti,tk,tj,nfld), s_out(ti,tk,tj,nfld), f_in(ti,tk,tj,4))
    allocate(u_pk(nfld*nn), g_pk(nfld*nn), xland2(ti,tj))

    ! distinct per-column warm-active state (field order th,qv,qc,qr,...,bg)
    do j = 1, tj
      do k = 1, tk
        do i = 1, ti
          colf = real(1 + (i-1) + 2*(j-1), c_double)               ! column flavor
          s_in(i,k,j, 1) = 295.0_c_double + 1.5_c_double*colf + 2.0_c_double*real(k-1,c_double) ! th
          s_in(i,k,j, 2) = 1.2e-2_c_double + 1.0e-3_c_double*colf  ! qv
          s_in(i,k,j, 3) = 8.0e-4_c_double + 1.0e-4_c_double*colf  ! qc
          s_in(i,k,j, 4) = 5.0e-5_c_double + 1.0e-5_c_double*colf  ! qr
          s_in(i,k,j, 5) = 0.0_c_double                            ! qi
          s_in(i,k,j, 6) = 0.0_c_double                            ! qs
          s_in(i,k,j, 7) = 0.0_c_double                            ! qg
          s_in(i,k,j, 8) = 1.0e9_c_double                          ! nccn
          s_in(i,k,j, 9) = 1.0e8_c_double + 1.0e7_c_double*colf    ! nc
          s_in(i,k,j,10) = 0.0_c_double                            ! ni
          s_in(i,k,j,11) = 1.0e4_c_double                          ! nr
          s_in(i,k,j,12) = 0.0_c_double                            ! bg
          f_in(i,k,j, 1) = 1.05_c_double                           ! rho
          f_in(i,k,j, 2) = 0.97_c_double                           ! pii
          f_in(i,k,j, 3) = 8.8e4_c_double                          ! p
          f_in(i,k,j, 4) = 500.0_c_double                          ! delz
        end do
      end do
    end do
    xland2 = 2.0_c_double                                          ! all-sea

    rc = kdm6_step_ad(s_in, f_in, ti, tk, tj, dt, 0_c_int, &
                      s_out, th_handle, xland2, 100.0_c_double, 10.0_c_double)
    if (rc /= KDM6_OK .or. .not. c_associated(th_handle)) then
       print *, "FAIL: kdm6_step_ad (tile) rc/handle ", rc
       stop 1
    end if

    ! covector u = e_{qv at (i0,k0,j0)} — single Fortran cell, field qv (=2).
    ! packed index (1-based) = (field-1)*nn + cell0 + 1; cell0 = Fortran col-major.
    u_pk = 0.0_c_double
    g_pk = 0.0_c_double
    cell0 = (i0-1) + ti*((k0-1) + tk*(j0-1))
    u_pk((2-1)*nn + cell0 + 1) = 1.0_c_double

    rc = kdm6_handle_vjp(th_handle, u_pk, g_pk)
    if (rc /= KDM6_OK) then
       print *, "FAIL: kdm6_handle_vjp (tile) rc ", rc
       stop 1
    end if

    ! gradient support must be confined to column (i0,j0) across ALL fields —
    ! a scrambled (im,kme,jme) layout would leak support to another column.
    any_in_col = .false.
    do fld = 1, nfld
      do j = 1, tj
        do k = 1, tk
          do i = 1, ti
            cell0 = (i-1) + ti*((k-1) + tk*(j-1))
            pidx  = (fld-1)*nn + cell0 + 1
            if (.not. ieee_is_finite(g_pk(pidx))) then        ! fp64 path: non-finite = contract breach
               print *, "FAIL: non-finite (NaN/Inf) in fp64 tile VJP gradient at i,k,j,fld=", i, k, j, fld
               stop 1
            end if
            if (g_pk(pidx) /= 0.0_c_double) then
               if (i /= i0 .or. j /= j0) then
                  print *, "FAIL: VJP support leaked outside column at i,k,j,fld=", i, k, j, fld
                  stop 1
               end if
               any_in_col = .true.
            end if
          end do
        end do
      end do
    end do
    if (.not. any_in_col) then
       print *, "FAIL: VJP support empty on tile (sensitivity/layout lost)"
       stop 1
    end if
    print *, "  PASS: kdm6_step_ad (2,3,4)-tile VJP support confined to source column (axis-swap sensitive)"

    ! VALUE-LEVEL layout check: column (i0,j0) run STANDALONE (im=1) must reproduce
    ! the embedded tile's (i0,j0) column forward output (column independence).
    ! Because the inputs are authored through Fortran NATIVE x(i,k,j,field) assumed-shape
    ! arrays (the compiler lays out the flat buffer, not manual offset math), this is a
    ! stronger, more independent layout oracle than the C++ self-consistent packed-buffer
    ! test: it catches wrapper-axis / (i,j)-stride / field-order mistakes that change the
    ! embedded-vs-standalone column values. It is NOT a complete proof of every internal
    ! convention, though — a *consistent* per-(field,k)/forcing mislabeling applied
    ! identically to both the embedded and standalone runs still cancels out.
    standalone: block
      real(c_double), allocatable :: sa_in(:,:,:,:), sa_out(:,:,:,:), sa_f(:,:,:,:)
      real(c_float),  allocatable :: sa_xland(:,:)
      type(c_ptr) :: sa_handle
      real(c_double) :: ref, dev, tol
      integer :: kk, ff
      allocate(sa_in(1,tk,1,nfld), sa_out(1,tk,1,nfld), sa_f(1,tk,1,4), sa_xland(1,1))
      do ff = 1, nfld
        do kk = 1, tk
          sa_in(1,kk,1,ff) = s_in(i0,kk,j0,ff)
        end do
      end do
      do ff = 1, 4
        do kk = 1, tk
          sa_f(1,kk,1,ff) = f_in(i0,kk,j0,ff)
        end do
      end do
      sa_xland   = 2.0_c_double
      sa_out     = -777.0_c_double
      sa_handle  = c_null_ptr
      ! value_only=1 => same forward values as value_only=0, no handle kept; used
      ! here as a forward-value probe of column (i0,j0).
      rc = kdm6_step_ad(sa_in, sa_f, 1, tk, 1, dt, 1_c_int, &
                        sa_out, sa_handle, sa_xland, 100.0_c_double, 10.0_c_double)
      if (rc /= KDM6_OK) then
         print *, "FAIL: standalone kdm6_step_ad rc ", rc
         stop 1
      end if
      if (c_associated(sa_handle)) then          ! value_only=1 contract: NULL handle
         print *, "FAIL: standalone value_only=1 returned non-null handle"
         stop 1
      end if
      ! column independence is exact; the comparison is asserted numerically equal
      ! within a 1e-12 relative tolerance (absorbs any benign batch fp noise), while
      ! a layout/ordering bug gives an O(1) deviation and FAILS.
      do ff = 1, nfld
        do kk = 1, tk
          ref = s_out(i0,kk,j0,ff)
          dev = abs(sa_out(1,kk,1,ff) - ref)
          tol = 1.0e-12_c_double * max(1.0_c_double, abs(ref))
          if (.not. (dev <= tol)) then
             print *, "FAIL: standalone /= embedded column at k,fld=", kk, ff, " dev=", dev, " ref=", ref
             stop 1
          end if
        end do
      end do
      print *, "  PASS: standalone column reproduces embedded (i0,j0) output (value-level layout)"
      deallocate(sa_in, sa_out, sa_f, sa_xland)
    end block standalone

    rc = kdm6_handle_close(th_handle)
    if (rc /= KDM6_OK) then
       print *, "FAIL: kdm6_handle_close (tile) returned ", rc
       stop 1
    end if

    deallocate(s_in, s_out, f_in, u_pk, g_pk, xland2)
  end block tile_test

  print *, "All Fortran ISO_C_BINDING tests passed."
end program test_fortran_smoke
