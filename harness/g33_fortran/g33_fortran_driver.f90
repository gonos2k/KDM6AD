! G3.3-M standalone Fortran driver (P1): run the reference legacy sedimentation
! path (module_mp_kdm6::kdm6) on a deterministic B=3, K=4 fixture and print the
! resulting prognostic state + surface precip as raw uint32 hex — the format the
! four-case G3.3-M comparator will read. Fortran-only: no C++/libtorch linkage.
!
! This is the build/run feasibility foundation (protocol §5, P1). Instrumenting
! the per-op sedimentation ladder is P2 (a temporary patched overlay).
module g33_fixture
  use, intrinsic :: iso_fortran_env, only: int32
  use module_model_constants, only: g, cp, cpv, r_d, r_v, svpt0, ep_1, ep_2, &
                                    xls, xlv, xlf, rhoair0, rhowater,        &
                                    rhosnow, cliq, cice, psat,               &
                                    wrf_eps => epsilon
  use module_mp_kdm6, only: kdm6
  implicit none
  integer, parameter :: NFLD_ST = 12
  character(len=4), dimension(NFLD_ST), parameter :: FLDNAME = &
       [character(len=4) :: 'th  ','qv  ','qc  ','qr  ','qi  ','qs  ', &
                            'qg  ','nccn','nc  ','ni  ','nr  ','bg  ']
  real, parameter :: CCN0_NL = 7.0e7, SCALEH_NL = 750.0
  real, parameter :: NCMIN_LAND_NL = 10.0, NCMIN_SEA_NL = 10.0
contains

  subroutine run_legacy(im, km, delt, outF, precF)
    integer, intent(in)  :: im, km
    real,    intent(in)  :: delt
    real,    intent(out) :: outF(im, km, NFLD_ST), precF(3, im)
    real, dimension(1:im,1:km,1:1) :: th, q, qc, qr, qi, qs, qg
    real, dimension(1:im,1:km,1:1) :: nn, nc, ni, nr, bg, diag_rhog
    real, dimension(1:im,1:km,1:1) :: den, pii, p, delz
    real, dimension(1:im,1:km,1:1) :: refl, re_c, re_i, re_s
    real, dimension(1:im,1:1)      :: xland, rainF, rainncv, snowF, snowncv
    real, dimension(1:im,1:1)      :: srF, graupelF, graupelncv
    integer :: i, k

    ! deterministic fixture: three columns with rain + a little ice/snow so the
    ! rain/number sedimentation path is exercised. Top-first is handled inside.
    do i = 1, im
      do k = 1, km
        th(i,k,1)   = 285.0 + real(i)          ! potential temperature
        q(i,k,1)    = 5.0e-3                    ! water vapour
        qc(i,k,1)   = 1.0e-4
        qr(i,k,1)   = 2.0e-4 * real(k)          ! rain, varies with level
        qi(i,k,1)   = 1.0e-6
        qs(i,k,1)   = 3.0e-5
        qg(i,k,1)   = 1.5e-5
        nn(i,k,1)   = 1.0e9
        nc(i,k,1)   = 1.0e8
        ni(i,k,1)   = 4.0e3
        nr(i,k,1)   = 2.0e3 * real(k)
        bg(i,k,1)   = 0.0
        diag_rhog(i,k,1) = 0.0
        den(i,k,1)  = 1.0 + 0.05 * real(km - k) ! denser lower down
        pii(i,k,1)  = 0.95
        p(i,k,1)    = 9.0e4
        delz(i,k,1) = 300.0 + 10.0 * real(k)
        refl(i,k,1) = 0.0
      end do
      xland(i,1) = 1.0
      rainF(i,1) = 0.0;  rainncv(i,1) = 0.0
      snowF(i,1) = 0.0;  snowncv(i,1) = 0.0
      srF(i,1)   = 0.0;  graupelF(i,1) = 0.0;  graupelncv(i,1) = 0.0
      re_c(i,:,1) = 0.0; re_i(i,:,1) = 0.0; re_s(i,:,1) = 0.0
    end do

    call kdm6(th=th, q=q, qc=qc, qr=qr, qi=qi, qs=qs, qg=qg,                &
              nn=nn, nc=nc, ni=ni, nr=nr, bg=bg, diag_rhog=diag_rhog,       &
              den=den, pii=pii, p=p, delz=delz,                             &
              delt=delt, g=g, cpd=cp, cpv=cpv, ccn0=CCN0_NL,                &
              rd=r_d, rv=r_v, t0c=svpt0,                                    &
              ep1=ep_1, ep2=ep_2, qmin=wrf_eps,                             &
              xls=xls, xlv0=xlv, xlf0=xlf, den0=rhoair0, denr=rhowater,     &
              scale_h=SCALEH_NL,                                            &
              ncmin_land=NCMIN_LAND_NL, ncmin_sea=NCMIN_SEA_NL,             &
              cliq=cliq, cice=cice, psat=psat,                              &
              xland=xland,                                                  &
              rain=rainF, rainncv=rainncv,                                  &
              snow=snowF, snowncv=snowncv, sr=srF,                          &
              refl_10cm=refl, diagflag=.false., do_radar_ref=0,             &
              graupel=graupelF, graupelncv=graupelncv,                      &
              itimestep=1,                                                  &
              has_reqc=0, has_reqi=0, has_reqs=0,                           &
              re_cloud=re_c, re_ice=re_i, re_snow=re_s,                     &
              ids=1, ide=im, jds=1, jde=1, kds=1, kde=km,                   &
              ims=1, ime=im, jms=1, jme=1, kms=1, kme=km,                   &
              its=1, ite=im, jts=1, jte=1, kts=1, kte=km)

    outF(:,:,1)  = th(:,:,1);  outF(:,:,2)  = q(:,:,1)
    outF(:,:,3)  = qc(:,:,1);  outF(:,:,4)  = qr(:,:,1)
    outF(:,:,5)  = qi(:,:,1);  outF(:,:,6)  = qs(:,:,1)
    outF(:,:,7)  = qg(:,:,1);  outF(:,:,8)  = nn(:,:,1)
    outF(:,:,9)  = nc(:,:,1);  outF(:,:,10) = ni(:,:,1)
    outF(:,:,11) = nr(:,:,1);  outF(:,:,12) = bg(:,:,1)
    precF(1,:) = rainncv(:,1)
    precF(2,:) = snowncv(:,1)
    precF(3,:) = graupelncv(:,1)
  end subroutine run_legacy
end module g33_fixture

program g33_fortran_driver
  use, intrinsic :: iso_fortran_env, only: int32
  use module_model_constants, only: cliq, cpv, rhoair0, rhowater, rhosnow
  use module_mp_kdm6, only: kdm6init
  use g33_fixture
  implicit none
  integer, parameter :: IM = 3, KM = 4
  real :: outF(IM, KM, NFLD_ST), precF(3, IM)
  integer :: i, k, f
  integer(int32) :: bits

  call kdm6init(rhoair0, rhowater, rhosnow, cliq, cpv, CCN0_NL, 0, .true.)
  call run_legacy(IM, KM, 20.0, outF, precF)

  ! Raw-bit stream (uint32 hex) — the operand-domain values the comparator reads.
  write(*,'(A)') 'G33-FORTRAN-BEGIN legacy'
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        bits = transfer(outF(i,k,f), 0_int32)
        write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'FLD', FLDNAME(f), i, k, bits
      end do
    end do
  end do
  do f = 1, 3
    do i = 1, IM
      bits = transfer(precF(f,i), 0_int32)
      write(*,'(A,1X,I0,1X,I0,1X,Z8.8)') 'PREC', f, i, bits
    end do
  end do
  write(*,'(A)') 'G33-FORTRAN-END legacy'
  write(*,'(A)') 'FORTRAN DRIVER OK (legacy, B=3 K=4)'
end program g33_fortran_driver
