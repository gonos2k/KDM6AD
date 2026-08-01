! Timestep-refinement leg: the SAME total 300 s reached in N kernel calls.
!
! Owner review §9. The open question after the `cpm`/`xl` finding is not parity
! but which discrete operator converges: the reference computes the thermodynamic
! coefficients once per kernel call and holds them across its internal subcycles,
! the port recomputes them each subcycle, and "recomputes more often" is not by
! itself an argument that the answer is better.
!
! The refinement is EXTERNAL — N calls of dt = 300/N — and that choice is what
! makes the experiment mean anything. Refining internally (one call, more
! subcycles) leaves the reference's coefficients pinned at the kernel-entry state
! for the whole 300 s, so its lag error cannot shrink and the comparison is
! rigged. Re-entering the kernel N times puts BOTH policies through F:893 N times,
! so both refresh, both approach the variable-coefficient limit, and the thing
! being measured is the RATE at which each does — which is the discriminating
! quantity. It is also the boundary §9 asks for: kdm62D directly, so the wrapper's
! preprocessing does not run N times and contaminate the sequence.
!
! N is a runtime argument. One build serves the whole sweep, so no member of it
! can differ by a compiler invocation.
!
! Deliberately a SEPARATE file from g33_fortran_driver.f90, which it otherwise
! duplicates. That driver's source hash is anchored in the four-leg bundle
! manifests, so adding a subroutine to it would invalidate the evidence this
! experiment is supposed to sit beside. The duplication is the cost of leaving
! the decision producer untouched.
!
! Emits one G33R STATE line per field/cell plus the three precipitation
! accumulators, in the same top-first convention as the decision driver.
module g33_refine
  use, intrinsic :: iso_fortran_env, only: int32
  use module_model_constants, only: g, cp, cpv, r_d, r_v, svpt0, ep_1, ep_2, &
                                    xls, xlv, xlf, rhoair0, rhowater,        &
                                    rhosnow, cliq, cice, psat
  use g33_fixture_v1, only: FIX_B => B, FIX_K => K, FIX_ID => FIXTURE_ID, &
       TH_BITS, QV_BITS, QC_BITS, QR_BITS, QI_BITS, QS_BITS, QG_BITS, &
       NCCN_BITS, NC_BITS, NI_BITS, NR_BITS, BG_BITS, RHO_BITS, PII_BITS, &
       P_BITS, DELZ_BITS, XLAND_BITS, DT_BITS, NCMIN_LAND_BITS, &
       NCMIN_SEA_BITS, QMIN_BITS, CCN0_BITS, SCALE_H_BITS
#ifdef KDM6_CONS
  use module_mp_kdm6_cons, only: kdm62D
#else
  use module_mp_kdm6, only: kdm62D
#endif
  implicit none
#ifdef KDM6_CONS
  character(len=*), parameter :: ALGOTAG = 'conservative'
#else
  character(len=*), parameter :: ALGOTAG = 'legacy'
#endif
  integer, parameter :: G33_B = FIX_B, G33_K = FIX_K, NFLD_ST = 12
  character(len=4), dimension(NFLD_ST), parameter :: FLDNAME = &
       [character(len=4) :: 'th  ','qv  ','qc  ','qr  ','qi  ','qs  ', &
                            'qg  ','nccn','nc  ','ni  ','nr  ','bg  ']
contains

  pure real function f32(bits) result(value)
    integer(int32), intent(in) :: bits
    value = transfer(bits, value)
  end function f32

  subroutine run_refined(im, km, nsplit, carry_aux, outF, precF)
    integer, intent(in)  :: im, km, nsplit
    logical, intent(in)  :: carry_aux
    real,    intent(out) :: outF(im, km, NFLD_ST), precF(3, im)
    real, dimension(1:im,1:km) :: den, pii, p, delz
    real, dimension(1:im,1:1)  :: xland, rainF, rainncv, snowF, snowncv
    real, dimension(1:im,1:1)  :: srF, graupelF, graupelncv
    real, dimension(1:im,1:km)   :: tk, qk, brsk, rhoxk, cmgk
    real, dimension(1:im,1:km,3) :: qcik, qrsk, ncik, nrsk
    real, dimension(1:im,1:km)   :: n0so2d, n0go2d
    real :: dt_total, delt, ccn0, ncmin_land, ncmin_sea, qmin
    integer :: i, k, kt, s

    if (im /= G33_B .or. km /= G33_K) error stop 'shared fixture dimensions differ'
    dt_total = f32(DT_BITS)
    ! Exact in f32 for every N in the sweep (300/1,2,3,6,12 = 300,150,100,50,25),
    ! so no member of the sequence carries a division rounding the others do not.
    delt = dt_total / real(nsplit)
    ccn0 = f32(CCN0_BITS)
    ncmin_land = f32(NCMIN_LAND_BITS); ncmin_sea = f32(NCMIN_SEA_BITS)
    qmin = f32(QMIN_BITS)

    ! Same top-first permutation as the decision driver.
    do i = 1, im
      do k = 1, km
        kt = km - k + 1
        pii(i,k) = f32(PII_BITS(i,kt))
        tk(i,k)  = f32(TH_BITS(i,kt)) * pii(i,k)
        qk(i,k)  = f32(QV_BITS(i,kt))
        qcik(i,k,1) = f32(QC_BITS(i,kt)); qcik(i,k,2) = f32(QI_BITS(i,kt))
        qcik(i,k,3) = 0.0
        qrsk(i,k,1) = f32(QR_BITS(i,kt)); qrsk(i,k,2) = f32(QS_BITS(i,kt))
        qrsk(i,k,3) = f32(QG_BITS(i,kt))
        ncik(i,k,1) = f32(NC_BITS(i,kt)); ncik(i,k,2) = f32(NI_BITS(i,kt))
        ncik(i,k,3) = f32(NCCN_BITS(i,kt))
        nrsk(i,k,1) = f32(NR_BITS(i,kt)); nrsk(i,k,2) = 0.0; nrsk(i,k,3) = 0.0
        brsk(i,k) = f32(BG_BITS(i,kt))
        den(i,k)  = f32(RHO_BITS(i,kt))
        p(i,k)    = f32(P_BITS(i,kt)); delz(i,k) = f32(DELZ_BITS(i,kt))
      end do
      xland(i,1) = f32(XLAND_BITS(i))
      ! Zeroed ONCE. rainF and the ncv accumulators are cumulative across the
      ! 300 s; re-zeroing per call would make the reported precipitation that of
      ! the final sub-step only, and the sequence would then compare different
      ! quantities at different N.
      rainF(i,1) = 0.0; rainncv(i,1) = 0.0; snowF(i,1) = 0.0; snowncv(i,1) = 0.0
      srF(i,1) = 0.0; graupelF(i,1) = 0.0; graupelncv(i,1) = 0.0
    end do
    rhoxk = 0.0; cmgk = 0.0; n0so2d = 0.0; n0go2d = 0.0

    do s = 1, nsplit
      ! The four kdm62D auxiliaries carry no intent in -- established by the
      ! sentinel matrix. `carry_aux` re-tests that across CALLS rather than within
      ! one: with .false. they are re-zeroed every call, with .true. whatever the
      ! kernel wrote survives. Identical output is the control; a difference means
      ! the no-intent-in finding does not extend to a multi-call sequence, and the
      ! whole refinement result would have to be read differently.
      if (.not. carry_aux) then
        rhoxk = 0.0; cmgk = 0.0; n0so2d = 0.0; n0go2d = 0.0
      end if
      call kdm62D(tk, qk, qcik, qrsk, ncik, nrsk, brsk, rhoxk, cmgk            &
                 ,den, p, delz                                                 &
                 ,delt, g, cp, cpv, ccn0, r_d, r_v, svpt0                      &
                 ,ep_1, ep_2, qmin                                             &
                 ,xls, xlv, xlf, rhoair0, rhowater                             &
                 ,cliq, cice, psat                                             &
                 ,1                                                            &
                 ,xland(:,1)                                                   &
                 ,ncmin_land, ncmin_sea                                        &
                 ,rainF(:,1), rainncv(:,1)                                     &
                 ,srF(:,1)                                                     &
                 ,1,im, 1,1, 1,km                                              &
                 ,1,im, 1,1, 1,km                                              &
                 ,1,im, 1,1, 1,km, n0so2d, n0go2d                              &
                 ,snowF(:,1), snowncv(:,1)                                     &
                 ,graupelF(:,1), graupelncv(:,1)                               &
                  )
    end do

    do i = 1, im
      do k = 1, km
        outF(i,k,1)  = tk(i,k) / pii(i,k)          ! back to theta, as the wrapper
        outF(i,k,2)  = qk(i,k)
        outF(i,k,3)  = qcik(i,k,1); outF(i,k,5) = qcik(i,k,2)
        outF(i,k,4)  = qrsk(i,k,1); outF(i,k,6) = qrsk(i,k,2)
        outF(i,k,7)  = qrsk(i,k,3); outF(i,k,8) = ncik(i,k,3)
        outF(i,k,9)  = ncik(i,k,1); outF(i,k,10) = ncik(i,k,2)
        outF(i,k,11) = nrsk(i,k,1); outF(i,k,12) = brsk(i,k)
      end do
    end do
    ! The CUMULATIVE arrays, not the ncv ones. kdm62D zeroes rainncv/snowncv/
    ! graupelncv at every kernel entry (F:914-917) and accumulates into rain/snow/
    ! graupel (F:1466-1467), so `ncv` after N calls is the last sub-call's
    ! precipitation alone. Reading it here would have compared 300 s of
    ! precipitation at N=1 against 25 s of it at N=12 -- a difference in call
    ! structure reported as a difference in the operator. The decision driver reads
    ! ncv correctly because it makes exactly one call.
    precF(1,:) = rainF(:,1); precF(2,:) = snowF(:,1); precF(3,:) = graupelF(:,1)
  end subroutine run_refined

  subroutine emit_fld(name, i, k, v)
    character(len=*), intent(in) :: name
    integer, intent(in) :: i, k
    real,    intent(in) :: v
    integer(int32) :: b
    b = transfer(v, b)
    write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R STATE', trim(name), i, k, b
  end subroutine emit_fld

end module g33_refine


program g33_refine_driver
  use module_model_constants, only: cliq, cpv, rhoair0, rhowater, rhosnow
#ifdef KDM6_CONS
  use module_mp_kdm6_cons, only: kdm6init => kdm6init_cons
#else
  use module_mp_kdm6, only: kdm6init
#endif
  use g33_refine
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  integer, parameter :: IM = G33_B, KM = G33_K
  real :: outF(IM,KM,NFLD_ST), precF(3,IM)
  character(len=32) :: arg
  integer :: nsplit, i, k, f, ios
  integer(int32) :: b
  logical :: carry_aux

  if (command_argument_count() < 1) error stop 'usage: g33_refine_driver NSPLIT [carry]'
  call get_command_argument(1, arg)
  read(arg, *, iostat=ios) nsplit
  if (ios /= 0 .or. nsplit < 1) error stop 'NSPLIT must be a positive integer'
  carry_aux = .false.
  if (command_argument_count() >= 2) then
    call get_command_argument(2, arg)
    carry_aux = (trim(arg) == 'carry')
  end if

  call kdm6init(rhoair0, rhowater, rhosnow, cliq, cpv, f32(CCN0_BITS), 0, .true.)
  call run_refined(IM, KM, nsplit, carry_aux, outF, precF)

  write(*,'(A,1X,I0,1X,A,1X,A)') 'G33R BEGIN nsplit', nsplit, &
       merge('carry  ', 'rezero ', carry_aux), ALGOTAG
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        call emit_fld(FLDNAME(f), i, KM-k, outF(i,k,f))
      end do
    end do
  end do
  do f = 1, 3
    do i = 1, IM
      b = transfer(precF(f,i), b)
      write(*,'(A,1X,I0,1X,I0,1X,Z8.8)') 'G33R PREC', f, i, b
    end do
  end do
  write(*,'(A)') 'G33R END'
end program g33_refine_driver
