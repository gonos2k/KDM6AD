! Standalone Fortran leg of the shared four-backend G3.3-M fixture.
! The initial state, forcing and common call parameters are generated from the
! same raw-bit authority as the C++ driver. The fixture is arithmetic-synthetic,
! not a meteorological replay.
module g33_fixture
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
  ! only the wrapper is renamed in the conservative module; the kernel keeps
  ! its name, so both variants export kdm62D under the same identifier
  use module_mp_kdm6_cons, only: kdm6 => kdm6_cons, kdm62D
#else
  use module_mp_kdm6, only: kdm6, kdm62D
#endif
  implicit none
#ifdef KDM6_CONS
  character(len=*), parameter :: ALGOTAG = 'conservative'
#else
  character(len=*), parameter :: ALGOTAG = 'legacy'
#endif
  integer, parameter :: G33_B = FIX_B, G33_K = FIX_K
  integer(int32), parameter :: G33_CCN0_BITS = CCN0_BITS
  character(len=*), parameter :: G33_FIXTURE_ID = FIX_ID
  integer, parameter :: NFLD_ST = 12
  character(len=4), dimension(NFLD_ST), parameter :: FLDNAME = &
       [character(len=4) :: 'th  ','qv  ','qc  ','qr  ','qi  ','qs  ', &
                            'qg  ','nccn','nc  ','ni  ','nr  ','bg  ']
contains

  pure real function f32(bits) result(value)
    integer(int32), intent(in) :: bits
    value = transfer(bits, value)
  end function f32

  subroutine run_case(im, km, outF, precF)
    integer, intent(in)  :: im, km
    real,    intent(out) :: outF(im, km, NFLD_ST), precF(3, im)
    real, dimension(1:im,1:km,1:1) :: th, q, qc, qr, qi, qs, qg
    real, dimension(1:im,1:km,1:1) :: nn, nc, ni, nr, bg, diag_rhog
    real, dimension(1:im,1:km,1:1) :: den, pii, p, delz
    real, dimension(1:im,1:km,1:1) :: refl, re_c, re_i, re_s
    real, dimension(1:im,1:1)      :: xland, rainF, rainncv, snowF, snowncv
    real, dimension(1:im,1:1)      :: srF, graupelF, graupelncv
    real, dimension(1:im,1:km,NFLD_ST) :: inF
    ! KERNEL-ENTRY locals: the 2-D arrays kdm62D takes. The wrapper builds these
    ! itself; calling the kernel directly means building them here — and NOT
    ! applying the wrapper's height-dependent CCN profile, which is the one
    ! transform the C++ port has no counterpart for and the only reason the two
    ! legs entered the kernel with different nccn.
    real, dimension(1:im,1:km)   :: tk, qk, brsk, rhoxk, cmgk
    real, dimension(1:im,1:km,3) :: qcik, qrsk, ncik, nrsk
    real, dimension(1:im,1:km)   :: n0so2d, n0go2d
    real :: delt, ccn0, scale_h, ncmin_land, ncmin_sea, qmin
    integer :: i, k, kt, f

    if (im /= G33_B .or. km /= G33_K) error stop 'shared fixture dimensions differ'
    delt=f32(DT_BITS); ccn0=f32(G33_CCN0_BITS); scale_h=f32(SCALE_H_BITS)
    ncmin_land=f32(NCMIN_LAND_BITS); ncmin_sea=f32(NCMIN_SEA_BITS)
    qmin=f32(QMIN_BITS)

    ! The authority is top-first (kt=1..K); the reference arrays are bottom-up.
    ! One explicit permutation is applied to every physical field. The actual p
    ! profile is the vertical anchor and qv is the column anchor—no detached
    ! self-reported anchor values exist.
    do i=1,im
      do k=1,km
        kt=km-k+1
        th(i,k,1)=f32(TH_BITS(i,kt)); q(i,k,1)=f32(QV_BITS(i,kt))
        qc(i,k,1)=f32(QC_BITS(i,kt)); qr(i,k,1)=f32(QR_BITS(i,kt))
        qi(i,k,1)=f32(QI_BITS(i,kt)); qs(i,k,1)=f32(QS_BITS(i,kt))
        qg(i,k,1)=f32(QG_BITS(i,kt)); nn(i,k,1)=f32(NCCN_BITS(i,kt))
        nc(i,k,1)=f32(NC_BITS(i,kt)); ni(i,k,1)=f32(NI_BITS(i,kt))
        nr(i,k,1)=f32(NR_BITS(i,kt)); bg(i,k,1)=f32(BG_BITS(i,kt))
        den(i,k,1)=f32(RHO_BITS(i,kt)); pii(i,k,1)=f32(PII_BITS(i,kt))
        p(i,k,1)=f32(P_BITS(i,kt)); delz(i,k,1)=f32(DELZ_BITS(i,kt))
        diag_rhog(i,k,1)=0.0; refl(i,k,1)=0.0
      end do
      xland(i,1)=f32(XLAND_BITS(i))
      rainF(i,1)=0.0; rainncv(i,1)=0.0; snowF(i,1)=0.0; snowncv(i,1)=0.0
      srF(i,1)=0.0; graupelF(i,1)=0.0; graupelncv(i,1)=0.0
      re_c(i,:,1)=0.0; re_i(i,:,1)=0.0; re_s(i,:,1)=0.0
    end do

    ! Only parameters with an actual C++ runtime counterpart are cross-tree PARAM
    ! records. ccn0/scale_h remain pinned by the fixture manifest and provenance.
    inF(:,:,1)=th(:,:,1); inF(:,:,2)=q(:,:,1); inF(:,:,3)=qc(:,:,1)
    inF(:,:,4)=qr(:,:,1); inF(:,:,5)=qi(:,:,1); inF(:,:,6)=qs(:,:,1)
    inF(:,:,7)=qg(:,:,1); inF(:,:,8)=nn(:,:,1); inF(:,:,9)=nc(:,:,1)
    inF(:,:,10)=ni(:,:,1); inF(:,:,11)=nr(:,:,1); inF(:,:,12)=bg(:,:,1)
    write(*,'(A)') 'G33F BEGIN v6 '//ALGOTAG
    ! WHICH BOUNDARY this run is evidence for. The kernel and wrapper paths answer
    ! different questions and their records are not interchangeable, so a stream that
    ! did not say which one it came from would let them be compared by accident.
    if (kernel_entry_mode()) then
      write(*,'(A)') 'G33F ENTRY kdm62d_kernel_entry_v1'
    else
      write(*,'(A)') 'G33F ENTRY kdm6_wrapper_input_v1'
    end if
    do f=1,NFLD_ST
      do k=1,km
        do i=1,im
          call emit_fld('G33F FIXIN', FLDNAME(f), i, km-k, inF(i,k,f))
        end do
      end do
    end do
    do k=1,km
      do i=1,im
        call emit_fld('G33F FIXIN', 'rho', i, km-k, den(i,k,1))
        call emit_fld('G33F FIXIN', 'pii', i, km-k, pii(i,k,1))
        call emit_fld('G33F FIXIN', 'p', i, km-k, p(i,k,1))
        call emit_fld('G33F FIXIN', 'delz', i, km-k, delz(i,k,1))
      end do
    end do
    do i=1,im
      call emit_fld('G33F FIXIN', 'xland', i, -1, xland(i,1))
    end do
    call emit_param('dt', delt)
    call emit_param('ncmin_land', ncmin_land)
    call emit_param('ncmin_sea', ncmin_sea)
    call emit_param('qmin', qmin)
    ! ccn0/scale_h have no C++ runtime counterpart, so they are NOT cross-tree
    ! PARAMs; but their ACTUAL runtime bits (not a re-hash of the authority JSON)
    ! must be recorded so the run manifest's Fortran-only hash is a measurement.
    call emit_localparam('ccn0', ccn0)
    call emit_localparam('scale_h', scale_h)

    if (kernel_entry_mode()) then
      ! KERNEL ENTRY. Everything the wrapper does before calling kdm62D, EXCEPT the
      ! height-dependent CCN profile that overwrites nccn — the one transform the
      ! C++ port has no counterpart for, and the reason the two legs were not
      ! comparing the same kernel input.
      do i = 1, im
        do k = 1, km
          tk(i,k)   = th(i,k,1) * pii(i,k,1)          ! wrapper F:379
          qk(i,k)   = q(i,k,1)
          qcik(i,k,1) = qc(i,k,1);  qcik(i,k,2) = qi(i,k,1);  qcik(i,k,3) = 0.
          qrsk(i,k,1) = qr(i,k,1);  qrsk(i,k,2) = qs(i,k,1);  qrsk(i,k,3) = qg(i,k,1)
          ncik(i,k,1) = nc(i,k,1);  ncik(i,k,2) = ni(i,k,1);  ncik(i,k,3) = nn(i,k,1)
          nrsk(i,k,1) = nr(i,k,1);  nrsk(i,k,2) = 0.;         nrsk(i,k,3) = 0.
          brsk(i,k)   = bg(i,k,1)
        end do
      end do
#ifdef KDM6_G33_FORTRAN_DUMP
      ! THE ACTUAL CALL ARGUMENTS, recorded here and nowhere else (owner P0-3).
      ! kdm62D's own entry padding (F:822-839) clamps the prognostics before the
      ! first outer_pre_sed snapshot, so that snapshot cannot tell "both backends
      ! were handed the same problem" from "they were handed different problems and
      ! the clamp erased the difference". These are the values as passed.
      do k = 1, km
        do i = 1, im
          call emit_kci('qv',   i, km-k, qk(i,k))
          call emit_kci('t',    i, km-k, tk(i,k))
          call emit_kci('qc',   i, km-k, qcik(i,k,1))
          call emit_kci('qi',   i, km-k, qcik(i,k,2))
          call emit_kci('qr',   i, km-k, qrsk(i,k,1))
          call emit_kci('qs',   i, km-k, qrsk(i,k,2))
          call emit_kci('qg',   i, km-k, qrsk(i,k,3))
          call emit_kci('nc',   i, km-k, ncik(i,k,1))
          call emit_kci('ni',   i, km-k, ncik(i,k,2))
          call emit_kci('nccn', i, km-k, ncik(i,k,3))
          call emit_kci('nr',   i, km-k, nrsk(i,k,1))
          call emit_kci('brs',  i, km-k, brsk(i,k))
          call emit_kci('p',    i, km-k, p(i,k,1))
          call emit_kci('rho',  i, km-k, den(i,k,1))
          call emit_kci('delz', i, km-k, delz(i,k,1))
        end do
      end do
#endif
      call kdm62D(tk, qk, qcik, qrsk, ncik, nrsk, brsk, rhoxk, cmgk            &
                 ,den(:,:,1), p(:,:,1), delz(:,:,1)                            &
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
      ! unpack, mirroring the wrapper's own pack-out
      do i = 1, im
        do k = 1, km
          th(i,k,1) = tk(i,k) / pii(i,k,1)
          q(i,k,1)  = qk(i,k)
          qc(i,k,1) = qcik(i,k,1); qi(i,k,1) = qcik(i,k,2)
          qr(i,k,1) = qrsk(i,k,1); qs(i,k,1) = qrsk(i,k,2); qg(i,k,1) = qrsk(i,k,3)
          nc(i,k,1) = ncik(i,k,1); ni(i,k,1) = ncik(i,k,2); nn(i,k,1) = ncik(i,k,3)
          nr(i,k,1) = nrsk(i,k,1); bg(i,k,1) = brsk(i,k)
        end do
      end do
    else
    call kdm6(th=th, q=q, qc=qc, qr=qr, qi=qi, qs=qs, qg=qg,                &
              nn=nn, nc=nc, ni=ni, nr=nr, bg=bg, diag_rhog=diag_rhog,       &
              den=den, pii=pii, p=p, delz=delz,                             &
              delt=delt, g=g, cpd=cp, cpv=cpv, ccn0=ccn0,                   &
              rd=r_d, rv=r_v, t0c=svpt0, ep1=ep_1, ep2=ep_2, qmin=qmin,     &
              xls=xls, xlv0=xlv, xlf0=xlf, den0=rhoair0, denr=rhowater,     &
              scale_h=scale_h, ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,  &
              cliq=cliq, cice=cice, psat=psat, xland=xland,                 &
              rain=rainF, rainncv=rainncv, snow=snowF, snowncv=snowncv,     &
              sr=srF, refl_10cm=refl, diagflag=.false., do_radar_ref=0,     &
              graupel=graupelF, graupelncv=graupelncv, itimestep=1,         &
              has_reqc=0, has_reqi=0, has_reqs=0,                           &
              re_cloud=re_c, re_ice=re_i, re_snow=re_s,                     &
              ids=1, ide=im, jds=1, jde=1, kds=1, kde=km,                   &
              ims=1, ime=im, jms=1, jme=1, kms=1, kme=km,                   &
              its=1, ite=im, jts=1, jte=1, kts=1, kte=km)
    end if

    outF(:,:,1)=th(:,:,1); outF(:,:,2)=q(:,:,1); outF(:,:,3)=qc(:,:,1)
    outF(:,:,4)=qr(:,:,1); outF(:,:,5)=qi(:,:,1); outF(:,:,6)=qs(:,:,1)
    outF(:,:,7)=qg(:,:,1); outF(:,:,8)=nn(:,:,1); outF(:,:,9)=nc(:,:,1)
    outF(:,:,10)=ni(:,:,1); outF(:,:,11)=nr(:,:,1); outF(:,:,12)=bg(:,:,1)
    precF(1,:)=rainncv(:,1); precF(2,:)=snowncv(:,1); precF(3,:)=graupelncv(:,1)
  end subroutine run_case

  ! Which comparison boundary this run is on. The kernel gate asks whether the
  ! CONSERVATIVE INTERFACE arithmetic differs between the backends at the same
  ! kernel entry; the wrapper path additionally carries kdm6's preprocessing, which
  ! the C++ port does not have and which is therefore a boundary question, not an
  ! arithmetic one. Two gates, two answers — so the mode is explicit, never implied.
  logical function kernel_entry_mode()
    character(len=32) :: mode
    call get_environment_variable('G33_ENTRY', mode)
    kernel_entry_mode = (trim(mode) == 'kernel')
  end function kernel_entry_mode

  subroutine emit_fld(tag, name, i, k_top, val)
    character(len=*), intent(in) :: tag, name
    integer, intent(in) :: i, k_top
    real, intent(in) :: val
    write(*,'(A,1X,A,2(1X,I0),1X,A,1X,Z8.8)') tag, trim(name), i, k_top, 'f32', &
         transfer(val, 0_int32)
  end subroutine emit_fld

#ifdef KDM6_G33_FORTRAN_DUMP
  subroutine emit_kci(name, i, k_top, val)
    ! One kernel_call_input record. loop 0 / chain '-' / n 0: a kernel call happens
    ! once however many sub-cycles it takes, and 0 sorts before loop 1 the way
    ! final_output's 0 sorts after the last loop.
    character(len=*), intent(in) :: name
    integer, intent(in) :: i, k_top
    real, intent(in) :: val
    write(*,'(A,1X,A,2(1X,I0),1X,A,1X,Z8.8)') &
         'G33F STAGE 0 - kernel_call_input 0', trim(name), i, k_top, 'f32', &
         transfer(val, 0_int32)
  end subroutine emit_kci
#endif

  subroutine emit_param(name, val)
    character(len=*), intent(in) :: name
    real, intent(in) :: val
    write(*,'(A,1X,A,1X,A,1X,Z8.8)') 'G33F PARAM', trim(name), 'f32', &
         transfer(val, 0_int32)
  end subroutine emit_param

  subroutine emit_localparam(name, val)   ! Fortran-only param (no C++ counterpart)
    character(len=*), intent(in) :: name
    real, intent(in) :: val
    write(*,'(A,1X,A,1X,A,1X,Z8.8)') 'G33F LOCALPARAM', trim(name), 'f32', &
         transfer(val, 0_int32)
  end subroutine emit_localparam

  subroutine emit_prec(fam, i, val)
    integer, intent(in) :: fam, i
    real, intent(in) :: val
    write(*,'(A,2(1X,I0),1X,A,1X,Z8.8)') 'G33F PREC', fam, i, 'f32', &
         transfer(val, 0_int32)
  end subroutine emit_prec
end module g33_fixture

program g33_fortran_driver
  use module_model_constants, only: cliq, cpv, rhoair0, rhowater, rhosnow
#ifdef KDM6_CONS
  use module_mp_kdm6_cons, only: kdm6init => kdm6init_cons
#else
  use module_mp_kdm6, only: kdm6init
#endif
  use g33_fixture
  implicit none
  integer, parameter :: IM=G33_B, KM=G33_K
  real :: outF(IM,KM,NFLD_ST), precF(3,IM)
  integer :: i,k,f

  call kdm6init(rhoair0, rhowater, rhosnow, cliq, cpv, f32(G33_CCN0_BITS), 0, .true.)
  call run_case(IM, KM, outF, precF)
  do f=1,NFLD_ST
    do k=1,KM
      do i=1,IM
        call emit_fld('G33F STATE', FLDNAME(f), i, KM-k, outF(i,k,f))
      end do
    end do
  end do
  do f=1,3
    do i=1,IM
      call emit_prec(f, i, precF(f,i))
    end do
  end do
  write(*,'(A)') 'G33F END v6 '//ALGOTAG
  write(*,'(A)') 'FORTRAN DRIVER OK ('//ALGOTAG//', fixture='//G33_FIXTURE_ID//')'
end program g33_fortran_driver
