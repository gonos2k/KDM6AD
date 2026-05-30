#if ( RWORDSIZE == 4 )
#  define VREC vsrec
#  define VSQRT vssqrt
#else
#  define VREC vrec
#  define VSQRT vsqrt
#endif
!-------------------------------------------------------------------------------
   module module_mp_kdm6
!-------------------------------------------------------------------------------
!
   use module_mp_radar
   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG
!
!
!-------------------------------------------------------------------------------
!
!  constant   :
!
!    dtcldcr       - maximum time step for minor loops
!    n0r           - intercept parameter rain
!    n0s           - intercept parameter snow
!    n0g           - intercept parameter graupel
!    n0smax        - maximum n0s (t=-90C unlimited)
!    alpha         - 0.122 exponen factor for n0s
!    avtr, bvtr    - a constant for terminal velocity of rain
!    avts, bvts    - a constant for terminal velocity of snow
!    avtg, bvtg    - a constant for terminal velocity of graupel
!    lamdarmax     - limited maximum value for slope parameter of rain
!    lamdarmin     - limited minimum value for slope parameter of rain
!    lamdasmax     - limited maximum value for slope parameter of snow
!    lamdagmax     - limited maximum value for slope parameter of graupel
!    r0            - 8 microm  in contrast to 10 micro m
!    peaut         - collection efficiency
!    xncr          - maritime cloud in contrast to 3.e8 in tc80
!    xmyu          - the dynamic viscosity kg m-1 s-1 
!    dicon         - constant for the cloud-ice diamter
!    dimax         - limited maximum value for the cloud-ice diamter
!    pfrz1, pfrz2  - constant in Biggs freezing
!    qcrmin        - minimum values for qr and qs
!    ncmin         - minimum value for nc
!    nrmin         - minimum value for nr
!    eacsc         - now/cloud-water collection efficiency
!    qs0           - threshold amount for aggretion to occur
!    satmax        - maximum saturation value for CCN activation
!                    1.008 for maritime /1.0048 for conti 
!    actk          - parameter for the CCN activation
!    actr          - radius of activated CCN drops
!    ncrk1, ncrk2  - Long's collection kernel coefficient
!    di100, di600, di2000  - parameter related with accretion and collection 
!                            of cloud drops
!    di82          - dimater related with raindrops evaporation
!    di15          - auto conversion takes place beyond this diameter 
!
!-------------------------------------------------------------------------------
   real, parameter, private :: dtcldcr = 120.
!   real, parameter, private :: n0r     = 8.e6
   real, parameter, private :: n0s     = 2.e6
!   real, parameter, private :: n0g     = 4.e6
   real, parameter, private :: n0smax  =  1.e11
   real, parameter, private :: dens    = 100.0
   real, parameter, private :: deni    = 500.0
   real, parameter, private :: alpha   = .12
   real, parameter, private :: avtr    = 841.9
   real, parameter, private :: bvtr    = 0.8
   real, parameter, private :: fvtr    = 0. 
   real, parameter, private :: mur     = 1.
   real, parameter, private :: avts    = 11.72
   real, parameter, private :: bvts    = 0.41
   real, parameter, private :: mus = 0.
   real, parameter, private :: mug = 0.
   real, parameter, private :: dms = 3.
   real, parameter, private :: dmg = 3.
! realy introduced for cloud ice
   real, parameter, private :: avti    = 2710. 
   real, parameter, private :: bvti    = 1.0 
   real, parameter, private :: lamdacmax = 5.e5
   real, parameter, private :: lamdacmin = 1.2e4  !82micron
   real, parameter, private :: lamdarmax = 3.5e4  !82micron
   real, parameter, private :: lamdarmin = 9.61e2 !3000 micron
   real, parameter, private :: lamdasmax = 1.8e5  !10micron new
   real, parameter, private :: lamdaimax = 1.82e6 !1micron new
   real, parameter, private :: lamdaimin = 9.08e3   !200micron new
   real, parameter, private :: r0      = .8e-5
! yhlee
!   real, parameter, private :: peaut   = .55
   real, parameter, private :: peaut   = .40
   real, parameter, private :: xncr    = 3.e8
   real, parameter, private :: xncr0   = 5.e7
   real, parameter, private :: xncr1   = 5.e8
   real, parameter, private :: xmyu    = 1.718e-5
   real, parameter, private :: dicon   = 11.9
   real, parameter, private :: dimax   = 500.e-6
   real, parameter, private :: pfrz1   = 100.
   real, parameter, private :: pfrz2   = 0.66
   real, parameter, private :: qcrmin  = 1.e-9
! ncmin changed for th Autoconversion
!   real, parameter, private :: ncmin   = 1.e1
   real, parameter, private :: nrmin   = 1.e-2
   real, parameter, private :: nrmax   = 5.e7
   real, parameter, private :: ncmax   = 5.e10 
! collection efficiency, eacsi, eacgi, 
   real, parameter, private :: eacrc   = 1.0
   real, parameter, private :: eacic   = 1.0
   real, parameter, private :: eacsc   = 1.0
   real, parameter, private :: eacgc   = 1.0
   real, parameter, private :: eacri   = 1.0
   real, parameter, private :: eacir   = 1.0
   real, parameter, private :: eacsr   = 1.0
   real, parameter, private :: eacgr   = 1.0
   real, parameter, private :: eacrs   = 1.0
   real, parameter, private :: qs0     = 6.e-4
   real, parameter, private :: satmax  = 1.0048
   real, parameter, private :: actk    = 0.6
   real, parameter, private :: actr    = 1.5
   real, parameter, private :: ncrk1   = 3.03e3
   real, parameter, private :: ncrk2   = 2.59e15
   real, parameter, private :: eccbrk   = 1. 
   real, parameter, private :: di100   = 1.e-4
   real, parameter, private :: di150   = 1.5e-4
   real, parameter, private :: di50   = 0.5e-4
   real, parameter, private :: di600   = 6.e-4
   real, parameter, private :: di200   = 2.e-4
   real, parameter, private :: di2000  = 2000.e-6
   real, parameter, private :: di60    = 60.e-6  
   real, parameter, private :: di82    = 82.e-6
   real, parameter, private :: di15    = 15.e-6
   real, parameter, private :: Rispl    = 5.e-6 
   real, parameter, private :: Rinud    = 10.e-6 
   real, parameter, private :: di125    = 125.e-6 
   real, parameter, private :: muc = 2.
   real, parameter, private :: dmc = 3.
   real, parameter, private :: dmr = 3.
   real, parameter, private :: dmi = 3.0
   real, parameter, private :: mui = 0.  
   real, parameter, private :: evq = 3.29
   real, parameter, private :: fvq = 0.16 

   double precision, save ::  rslopermmax,rslopesmmax,rslopegmmax,rslopecmmax,rslopeimmax
   real,save  ::              rslopec2max,rslopec3max,rslopecdmax, &
                              rsloperdmax,rslopesdmax,rslopegdmax, &
                              rsloperbmax,rslopesbmax,             &
                              rsloper2max,rslopes2max,rslopeg2max, &
                              rsloper3max,rslopes3max,rslopeg3max, &
                              rslopei3max,rslopeidmax,rslopeibmax,rslopei2max
   real, save ::                                                               &
             mur1,g1pmr,mur2,g2pmr,mur3,g3pmr,mur4,g4pmr,mur7,g7pmr,           &
             muc1,g1pmc,muc3,g3pmc,muc4,g4pmc,muc6,g6pmc,muc9,g9pmc,           &
             mus1,g1pms,mus2,g2pms,mus3,g3pms,                                 &
             mug1,g1pmg,mug2,g2pmg,mug3,g3pmg,                                 &
             cmc, cmr,cmi,axni, bxni,                                          &
             cms,                                                              &
             qc0,qc1,qck1,pidnc,bvtr1,bvtr2,bvtr3,bvtr4,bvtr5,                 &
             bvtr6,bvtr7, bvtr2o5,bvtr3o5, brmur1,                             &
             drmur1, drmur2, drmur3,drbrmur1, drbrmur3,                        &
             dsmus1, dsmus2, dsmus3,dsbsmus1,                        &
             dgmug1,g1pdgmg,                                                   &
             g1pbr,g2pbr,g3pbr,g4pbr,g5pbr,g6pbr,g7pbr,g1pbrmr,                &
             g1pdrmr,g2pdrmr,g3pdrmr,g3pbrmr, g1pdrbrmr, g3pdrbrmr,g1p2drmr,   &
             g1pdsms,g2pdsms,g3pdsms,g1pdsbsms,g1p2dcomuc1,g1pdcomuc1,&
             g5pbro2,g7pbro2,pi,                                               &
             pvtr,pvtrn,eacrr,pidnr,                                           &
             precr1,precr2,xmmax,roqimax,bvts1,bvts2,                          &
             bvts3,bvts4,g1pbs,g3pbs,g4pbs,g5pbso2,                            &
             pvts,precs1,precs2,pidn0s,xlv1,pacrc,                             &
             pacrg,precg1,                          &
             n0g,deng,lamdagmax,                                     &
             rslopecmax,rslopermax,rslopesmax,rslopegmax,rslopeimax,           &
             g1pmi,mui1,xam_c,xbm_c,xmu_c,xam_i,      &
             xbm_i, xmu_i
  real, save :: pvtin, g1pbimi, bimui1, g1pdimi,g2pdimi,g3pdimi,                     &
                dimui1, dimui2, dimui3, pidni,pvti,g1pdibimi,                        &
                dibimui1,mui2,mui3,mui4,mui5,bvti3,g3pbi,g2pmi,g3pmi,g4pmi,g5pmi

  real   :: Nid !ice-nucleus concentrations depend on temperautre
  real   :: Nic !potential contact-freezing nuclei concentrations
  real   :: ratios !sublimation element
  real   :: ele1, ele2
  real,save   :: Minud  ! initial mass of nucleated crystal 
  real,save   :: Miaut  ! threshold mass for cloud ice aggregation 
  real,save   :: Mispl  ! mass of splintered ice particle
  real :: fmul ! parameter for rime-splintering
  real :: qi0 ! 
  real, parameter, private :: Rcn = 0.1e-6 ! radius of contact nuclei 
  real, parameter, private :: F1S= 0.66 ! ventilation facter
  real, parameter, private :: F2S =0.44 ! 
!
    contains
!===================================================================
!
    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &
                    nn, nc, ni, nr, bg, diag_rhog,         &
                    den, pii, p, delz,                     &
                    delt,g, cpd, cpv, ccn0, rd, rv, t0c,   &
                    ep1, ep2, qmin,                        &
                    xls, xlv0, xlf0, den0, denr,           &
                    scale_h,                               & !yhlee
                    ncmin_land,                            & !yhlee
                    ncmin_sea,                             & !yhlee
                    cliq,cice,psat,                        &
                    xland,                                 &
                    rain, rainncv,                         &
                    snow, snowncv,                         &
                    sr,                                    &
                    refl_10cm, diagflag, do_radar_ref,     &
                    graupel, graupelncv,                   &
                    itimestep,                             &
                    has_reqc, has_reqi, has_reqs,          &  ! for radiation
                    re_cloud, re_ice,   re_snow,           &  ! for radiation     
                    ids,ide, jds,jde, kds,kde,             &
                    ims,ime, jms,jme, kms,kme,             &
                    its,ite, jts,jte, kts,kte              &
                    )
!-------------------------------------------------------------------
   implicit none
!-------------------------------------------------------------------
   integer                                   , intent(in   ) :: itimestep
   integer                                   , intent(in   ) ::                &
                                                    ids,ide, jds,jde, kds,kde, &
                                                    ims,ime, jms,jme, kms,kme, &
                                                    its,ite, jts,jte, kts,kte
   real                                      , intent(in   ) :: delt, g, ccn0, &
                                                                rd, rv, t0c,   &
                                                                cpd, cpv,      &
                                                                den0, qmin,    &
                                                                ep1, ep2, xls, &
                                                                xlv0, xlf0,    &
                                                                cliq, cice,    &
                                                                psat, denr,    &
                                                                scale_h,       & ! yhlee
                                                                ncmin_land,    & ! yhlee
                                                                ncmin_sea  ! yhlee
   real, dimension(ims:ime,jms:jme)          , intent(in   ) :: xland
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: den
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: pii
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: p
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: delz
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: th
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: q
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qc
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qi
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qr
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qs
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qg
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nn
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nc
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: ni
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nr
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: bg
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: diag_rhog
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: rain
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: rainncv
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: sr
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: snow
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: snowncv
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: graupel
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: graupelncv

!
! for radiation connecting
!
   integer                                 , intent(in   ) :: has_reqc
   integer                                 , intent(in   ) :: has_reqi
   integer                                 , intent(in   ) :: has_reqs
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_cloud
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_ice
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_snow
!
! for reflectivity
!
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: refl_10cm
   logical                       , optional, intent(in   ) :: diagflag
   integer                       , optional, intent(in   ) :: do_radar_ref
!   
! local variables
!
   real, dimension(its:ite,kts:kte)   :: t
   real, dimension(its:ite,kts:kte,2) :: qci
   real, dimension(its:ite,kts:kte,3) :: nrs,nci
   real, dimension(its:ite,kts:kte,3) :: qrs
   real, dimension(its:ite,kts:kte)   :: n0so, n0go
   integer                            :: i,j,k
   real, dimension(its:ite,kts:kte) :: brs
   real, dimension(its:ite,kts:kte) :: rhox
   real, dimension(its:ite,kts:kte) :: cmg
!
! for reflectivity
!
   real, dimension(kts:kte) :: qv1d 
   real, dimension(kts:kte) :: t1d
   real, dimension(kts:kte) :: p1d
   real, dimension(kts:kte) :: qr1d
   real, dimension(kts:kte) :: nr1d
   real, dimension(kts:kte) :: qs1d
   real, dimension(kts:kte) :: qg1d
   real, dimension(kts:kte) :: n0so1d, n0go1d
   real, dimension(kts:kte) :: dBZ
   real, dimension(kts:kte) :: cmg1d
!
! to calculate effective radius for radiation
!
   real, dimension(kts:kte) :: qc1d, nc1d, den1d
   real, dimension(kts:kte) :: qi1d, ni1d
   real, dimension(kts:kte) :: re_qc, re_qi, re_qs
! 20250106 CCN init
   real :: z_sum
!
   if (itimestep .eq. 1) then 
! yhlee start
     do j = jms,jme
       do i = ims,ime
         z_sum=0.0
         do k = kms,kme    
           z_sum = z_sum + delz(i,k,j)
           if (xland(i,j)==1) then
             nn(i,k,j) = (5000.* exp(-0.4*z_sum/1000.)+100.)*1.e6
           else
             nn(i,k,j) = (150.*exp(-0.35*z_sum/1000.)+10.)*1.e6
           endif
!           nn(i,k,j) = ccn0
! yhlee end
         enddo
       enddo
     enddo
   endif
!
   ! KDM6AD step-1 forward-consistency dump (Fortran kdm6 path, pre-physics).
   ! Gated for production safety: fixed filename + STATUS='REPLACE' collides
   ! across MPI ranks and pollutes the working dir. Recompile with
   ! -DKDM6_FORWARD_PARITY_DUMP (or add to CPPFLAGS in configure.wrf) to
   ! re-enable for forensic comparison vs the kdm6ad path.
#ifdef KDM6_FORWARD_PARITY_DUMP
   if (itimestep .eq. 1) then
     open(unit=8801, file='kdm6_step1_kdm6_in.bin', form='unformatted', &
          access='stream', status='replace')
     write(8801) ims, ime, kms, kme, jms, jme
     write(8801) q
     write(8801) qc
     write(8801) qr
     write(8801) qi
     write(8801) qs
     write(8801) qg
     write(8801) nc
     write(8801) nr
     write(8801) ni
     write(8801) nn
     write(8801) bg
     write(8801) th
     close(8801)
   endif
#endif
!
   do j = jts,jte
     do k = kts,kte
       do i = its,ite
         t(i,k) = th(i,k,j)*pii(i,k,j)
         qci(i,k,1) = qc(i,k,j)
         qci(i,k,2) = qi(i,k,j)
         qrs(i,k,1) = qr(i,k,j)
         qrs(i,k,2) = qs(i,k,j)
         qrs(i,k,3) = qg(i,k,j)
         nci(i,k,1) = nc(i,k,j)
         nci(i,k,2) = ni(i,k,j)
         nci(i,k,3) = nn(i,k,j)
         nrs(i,k,1) = nr(i,k,j)     
         nrs(i,k,2) = 0. 
         nrs(i,k,3) = 0. 
         brs(i,k) = bg(i,k,j)
       enddo
     enddo   
     ! 
     !  Sending array starting locations of optional variables may cause
     !  troubles, so we explicitly change the call.
     !
     call kdm62D(t, q(ims,kms,j), qci, qrs, nci, nrs, brs, rhox, cmg  &
                ,den(ims,kms,j)                               &
                ,p(ims,kms,j), delz(ims,kms,j)                &
                ,delt,g, cpd, cpv, ccn0, rd, rv, t0c          &
                ,ep1, ep2, qmin                               &
                ,xls, xlv0, xlf0, den0, denr                  &
                ,cliq,cice,psat                               &
                ,j                                            &
                ,xland(ims,j)                                 &
                ,ncmin_land, ncmin_sea                        & !yhlee
                ,rain(ims,j),rainncv(ims,j)                   &
                ,sr(ims,j)                                    &
                ,ids,ide, jds,jde, kds,kde                    &
                ,ims,ime, jms,jme, kms,kme                    &
                ,its,ite, jts,jte, kts,kte,n0so,n0go          &
                ,snow(ims,j),snowncv(ims,j)                &
                ,graupel(ims,j),graupelncv(ims,j)          &
                )
!
     do k = kts,kte
       do i = its,ite
         th(i,k,j) = t(i,k)/pii(i,k,j)
         qc(i,k,j) = qci(i,k,1)
         qi(i,k,j) = qci(i,k,2)
         qr(i,k,j) = qrs(i,k,1)
         qs(i,k,j) = qrs(i,k,2)
         qg(i,k,j) = qrs(i,k,3)
         nr(i,k,j) = nrs(i,k,1)   
         nc(i,k,j) = nci(i,k,1)
         ni(i,k,j) = nci(i,k,2)
         nn(i,k,j) = nci(i,k,3)
         bg(i,k,j) = brs(i,k)
         diag_rhog(i,k,j) = rhox(i,k)
       enddo
     enddo
!
     if ( present (diagflag) ) then
       if (diagflag .and. do_radar_ref == 1) then
         do i = its,ite
           do k = kts,kte
             t1d(k)  = th(i,k,j)*pii(i,k,j)
             p1d(k)  = p(i,k,j)
             qv1d(k) = q(i,k,j)
             qr1d(k) = qr(i,k,j)
             nr1d(k) = nr(i,k,j)
             qs1d(k) = qs(i,k,j)
             n0so1d(k) = n0so(i,k)
             n0go1d(k) = n0go(i,k)
             qg1d(k) = qg(i,k,j)
             cmg1d(k) = cmg(i,k)
           enddo
           call refl10cm_kdm6 (qv1d, qr1d, nr1d, qs1d, qg1d, n0so1d,&
                              n0go1d, t1d, p1d, dBZ, kts, kte, i, j, cmg1d)
           do k = kts, kte
             refl_10cm(i,k,j) = max(-35., dBZ(k))
           enddo
         enddo
       endif
     endif
!
! calculate effective radius of cloud, ice, and snow 
!
     if (has_reqc.ne.0 .and. has_reqi.ne.0 .and. has_reqs.ne.0) then
       do i = its,ite
         do k = kts,kte
           re_qc(k) = RE_QC_BG
           re_qi(k) = RE_QI_BG
           re_qs(k) = RE_QS_BG
!
           t1d(k)  = th(i,k,j)*pii(i,k,j)
           den1d(k)= den(i,k,j)
           qc1d(k) = qc(i,k,j)
           qi1d(k) = qi(i,k,j)
           qs1d(k) = qs(i,k,j)
           nc1d(k) = nc(i,k,j)
           ni1d(k) = ni(i,k,j)
         enddo
!
         call effectRad_kdm6(t1d, qc1d, nc1d, qi1d, ni1d, qs1d, den1d,   &
                             qmin, t0c, re_qc, re_qi, re_qs,       &
                             kts, kte, i, j)
!
         do k = kts,kte
           re_cloud(i,k,j) = max(RE_QC_BG,  min(re_qc(k),  50.e-6))
           re_ice(i,k,j)   = max(RE_QI_BG, min(re_qi(k), 125.e-6))
           re_snow(i,k,j)  = max(RE_QS_BG,   min(re_qs(k), 999.e-6))
         enddo
       enddo
     endif
   enddo
!
   ! KDM6AD forward-consistency dumps (Fortran kdm6 path, post-physics).
   ! Gated — see pre-physics dump comment for rationale.
#ifdef KDM6_FORWARD_PARITY_DUMP
   if (itimestep .eq. 1 .or. itimestep .eq. 1440) then
     if (itimestep .eq. 1) then
       open(unit=8801, file='kdm6_step1_kdm6_out.bin', form='unformatted', &
            access='stream', status='replace')
     else
       open(unit=8801, file='kdm6_step1440_kdm6_out.bin', form='unformatted', &
            access='stream', status='replace')
     endif
     write(8801) ims, ime, kms, kme, jms, jme
     write(8801) q
     write(8801) qc
     write(8801) qr
     write(8801) qi
     write(8801) qs
     write(8801) qg
     write(8801) nc
     write(8801) nr
     write(8801) ni
     write(8801) nn
     write(8801) bg
     write(8801) th
     close(8801)
   endif
#endif
!
   end subroutine kdm6
!
!------------------------------------------------------------------------------
!
   subroutine kdm62D(t, q, qci, qrs, nci, nrs                     &
                   ,brs, rhox, cmg, den, p, delz                  &
                   ,delt,g, cpd, cpv, ccn0, rd, rv, t0c           &
                   ,ep1, ep2, qmin                                &
                   ,xls, xlv0, xlf0, den0, denr                   &
                   ,cliq,cice,psat                                &
                   ,lat                                           &
                   ,slmsk                                         &
                   ,ncmin_land, ncmin_sea                         & ! yhlee
                   ,rain,rainncv                                  &
                   ,sr                                            &
                   ,ids,ide, jds,jde, kds,kde                     &
                   ,ims,ime, jms,jme, kms,kme                     &
                   ,its,ite, jts,jte, kts,kte, n0so, n0go         &
                   ,snow,snowncv                                  &
                   ,graupel,graupelncv                            &
                    )
!------------------------------------------------------------------------------
    implicit none
!-------------------------------------------------------------------------------
!
!  This code is a KNU double-moment 6-class GRAUPEL phase 
!  microphyiscs scheme (kdm6). The WDM microphysics scheme predicts 
!  number concentrations for warm rain species including clouds and 
!  rain. cloud condensation nuclei (ccn) is also predicted.
!  The cold rain species including ice, snow, graupel follow the 
!  WRF single-moment 6-class microphysics (wsm6, Hong and Lim 2006)
!  in which theoretical background for WSM ice phase microphysics is 
!  based on Hong et al. (2004). A new mixed-phase terminal velocity
!  for precipitating ice is introduced in WSM6 (Dudhia et al. 2008). 
!  The WDM scheme is described in Lim and Hong (2010).
!
!  kdm6 cloud scheme
!
!  Coded by Kyo-Sun Lim and Song-You Hong (Yonsei Univ.) Fall 2008
!
!  Implemented by Kyo-Sun Lim and Jimy Dudhia (NCAR) Winter 2008
!
!  further modifications :
!        semi-lagrangian sedimentation (JH,2010),hong, aug 2009
!        ==> higher accuracy and efficient at lower resolutions
!        reflectivity computation from greg thompson, lim, jun 2011
!        ==> only dignostic, but with removal of too large drops
!        add hail option from afwa, aug 2014 
!        ==> switch graupel or hail by changing no, den, fall vel.
!        effetive radius of hydrometeors, bae from kiaps, jan 2015
!        ==> consistency in solar insolation of rrtmg radiation
!        bug fix in melting terms, bae from kiaps, nov 2015
!        ==> density of air is divided, which has not been
!        bug fix in sedimentation of rain, bae from kiaps, mar 2017
!        change autoconversion rate to equation, bae from kiaps, oct 2017
!        nccn > 100 cm-3, bae from kiaps, oct 2017
!        bug fix hydrometeros update before condensation process of rain,
!           bae from kiaps, oct2017
!        bug fix in snow melting and autoconversion
!        ==> Revisions enchance melting and autoconverison.
!           hong from noaa, july 2023
!        remedy for tiny nc in the presence of qc (nc = xncr, 300/cm**3)
!        ==> prevents the crash in computing autoconversion
!           hong from noaa, july 2023   
!
!  history log :
!
!  Reference) Lim and Hong (LH, 2010) Mon. Wea. Rev. 
!             Juang and Hong (JH, 2010) Mon. Wea. Rev.
!             Hong, Dudhia, Chen (HDC, 2004) Mon. Wea. Rev. 
!             Hong and Lim (HL, 2006) J. Korean Meteor. Soc. 
!             Cohard and Pinty (CP, 2000) Quart. J. Roy. Meteor. Soc.
!             Khairoutdinov and Kogan (KK, 2000) Mon. Wea. Rev.
!             Dudhia, Hong and Lim (DHL, 2008) J. Meteor. Soc. Japan
!             
!             Lin, Farley, Orville (LFO, 1983) J. Appl. Meteor.
!             Rutledge, Hobbs (RH83, 1983) J. Atmos. Sci.
!             Rutledge, Hobbs (RH84, 1984) J. Atmos. Sci.
!
!-------------------------------------------------------------------------------
! 
!  input :
!    deltim                       - timestep
!    g, cpd, cpv, t0c, den0,      - constant 
!    rd, rv, ep1, ep2, qmin, 
!    xls, xlv0, xlf0, denr,
!    cliq, cice, psat
!    ids, ide, jds, jde, kds, kde - dimension
!    ims, ime, jms, jme, kms, kme 
!    its, ite, jts, jte, kts, kte 
!    ncloud                       - number of hydrometeor
!    p                            - pressure, Pa
!    delz                         - depth of model layer, m
!   * with chemistry
!    slmsk                        - land/sea mask, 0: sea, 1: land
!    so4                          - mixing ratio of sulfate
!    ss                           - mixing ratio of sea salt
!    oc                           - mixing ratio of organic carbon
!    
!  inout : 
!    t1                           - temperautre
!    q1                           - specific humidity
!    q2                           - mixing ratio of cloud water, rain, ice, 
!                                   snow, and graupel
!                                   qc, qr, qi, qs, qg
!    n2                           - number concentration of ccn, cloud droplet,
!                                   and raindrop
!                                   nn, nc, nr
!    rain, rainncv                - precipitation
!    sr                           - ratio of snow to rain
!
!  all units are in m.k.s. and source/sink terms in kg kg-1 s-1.
!-------------------------------------------------------------------------------
   integer                                , intent(in   ) ::                  &
                                                   ids,ide, jds,jde, kds,kde, &
                                                   ims,ime, jms,jme, kms,kme, &
                                                   its,ite, jts,jte, kts,kte
   integer                                , intent(in   ) :: lat
   real                                   , intent(in   ) :: delt
   real                                   , intent(in   ) :: g, cpd, cpv, t0c, &
                                                             den0, rd, rv,     &
                                                             ep1, ep2, qmin,   &
                                                             xls, xlv0, xlf0,  &
                                                             cliq, cice, psat, &
                                                             denr,             &
                                                             ncmin_land, ncmin_sea ! yhlee
   real                                   , intent(in   ) :: ccn0
   real, dimension(ims:ime)               , intent(in   ) :: slmsk
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: p
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: delz
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: den
   real, dimension(its:ite,kts:kte)       , intent(inout) :: t
   real, dimension(its:ite,kts:kte,2)     , intent(inout) :: qci
   real, dimension(its:ite,kts:kte,3)     , intent(inout) :: qrs
   real, dimension(its:ite,kts:kte,3)     , intent(inout) :: nrs,nci
   real, dimension(its:ite,kts:kte)       , intent(inout) :: brs
   real, dimension(its:ite,kts:kte)       , intent(out) :: rhox
   real, dimension(ims:ime,kms:kme)       , intent(inout) :: q
   real, dimension(ims:ime)               , intent(inout) :: rain
   real, dimension(ims:ime)               , intent(inout) :: rainncv
   real, dimension(ims:ime)               , intent(inout) :: sr
   real, dimension(ims:ime), optional     , intent(inout) :: snow
   real, dimension(ims:ime), optional     , intent(inout) :: snowncv
   real, dimension(ims:ime), optional     , intent(inout) :: graupel
   real, dimension(ims:ime), optional     , intent(inout) :: graupelncv

!
!  local variables
! 
   real, dimension(its:ite,kts:kte) ::bvtg,rslopegbmax,dgbgmug1,  &
                                      bvtg1,bvtg2,bvtg3,bvtg4,g1pdgbgmg, &
                                      g1pbg,g3pbg,g4pbg,g5pbgo2
   real, dimension(its:ite,kts:kte) :: cmg,pidn0g
   real, dimension(its:ite,kts:kte) :: avtg,pvtg,precg2
   real, dimension(its:ite,kts:kte)   :: dend
   real, dimension(its:ite,kts:kte)   :: qcr
   real, dimension(its:ite,kts:kte)   :: sw
   real, dimension(its:ite,kts:kte,2) :: rh
   real, dimension(its:ite,kts:kte,3) :: qs
   real , dimension(its:ite,kts:kte,4) :: rslope, rslope2, rslope3, rslopeb,rsloped
   double precision, dimension(its:ite,kts:kte,4) :: rslopemu
   real, dimension(its:ite,kts:kte,4) :: falk, fall
   real, dimension(its:ite,kts:kte) :: falkb, fallb
   real, dimension(its:ite,kts:kte)   :: dbs,dbg
   double precision, dimension(its:ite,kts:kte,4) :: work1
   real, dimension(its:ite,kts:kte)   :: qci_tmp
   real, dimension(its:ite,kts:kte,3) :: qrs_tmp
   real, dimension(its:ite,kts:kte,3) :: avedia
   real, dimension(its:ite,kts:kte,2) :: sigma
   real, dimension(its:ite,kts:kte)   :: rslopec,rslopec2,rslopec3,rslopecd
   double precision, dimension(its:ite,kts:kte)   :: rslopecmu
   double precision, dimension(its:ite,kts:kte)   :: n0r, n0c, n0i
   real, dimension(its:ite,kts:kte)   :: n0so, n0go
   real, dimension(its:ite,kts:kte,2)   :: falln, falkn
   double precision, dimension(its:ite,kts:kte,2)   :: workn
   real, dimension(its:ite,kts:kte)   :: worka, workr
   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp
   real, dimension(its:ite,kts:kte) :: nrs_tmp,nci_tmp
   real, dimension(its:ite,kts:kte)   :: lamdr_tmp, lamdc_tmp, lamdi_tmp
   real, dimension(its:ite,kts:kte)   :: falkc, work1c, work2c
   real, dimension(its:ite,kts:kte)   :: dqr,dnr
   real, dimension(its:ite,kts:kte)   :: dqi,dni
   real, dimension(its:ite,kts:kte)   :: dqs,dqg
   real, dimension(its:ite,kts:kte)   :: pcact, psaut, pgaut, pgacs,        &
                                      pigen, pcond, paacw,pracw, prevp,     &
                                      praci, piacr, pracs,                  &
                                      psacr, pseml, pgacr, pgeml, praut,    &
                                      pgmlt, psmlt, pgaci, pgacw, pgdep,    &
                                      psaci, psacw, psdep, psevp, pgevp,    &
                                      pidep,pinud,pmulcs, pmulcg, pmulrs, pmulrg
   real, dimension(its:ite,kts:kte)   :: ncevp, ncact,                      &
                                      ngeml, nseml, nccol, nrcol, nracw,    &
                                      nraut, niacr, nsacr, ngacr, nsacw,    &
                                      naacw, ngacw, nraci, nsaci, ngaci,    &
                                      nracs, ninud, nsaut, nisub,           &
                                      nmulcs, nmulcg, nmulrs, nmulrg
!Prognostic Bg process
   real, dimension(its:ite,kts:kte)   :: braci,biacr,bracs,bsacr,           &
                                        bgacr,baacw,bsacw,bgacw,bgacs,bgaci,&
                                        bsaut,bsaci,bsdep,bgdep,bgaut,      &
                                        bsevp,bseml,bgevp,bgeml
!NI PROCESS
   real, dimension(its:ite,kts:kte)   :: piacw, niacw
   real, dimension(its:ite,kts:kte)   :: xl, cpm, work2, denfac, xni, n0sfac,  &
                                         qsum
   real, dimension(its:ite,kts:kte)   :: denqrs1, denqrs2, denqrs3
   real, dimension(its:ite,kts:kte)   :: denqr1, denncr3, denqci
   real, dimension(its:ite)           :: delqrs1, delqrs2, delqrs3, delncr3
   real, dimension(its:ite)           :: delqi
   real, dimension(its:ite)           :: tstepsnow, tstepgraup
   real                               :: gfac, sfac
   real, dimension(its:ite,kts:kte)   :: difa
   double precision   :: pinuc,ninuc

!
! top level for computing of cloud microphysical process
!
   integer                            :: kte_in
!
! variables for optimization
!
   real,    dimension(its:ite)        :: tvec1
   integer, dimension(its:ite)        :: mnstep, numndt
   integer, dimension(its:ite)        :: mstep, numdt
   integer, dimension(its:ite)        :: mstep_i, numdt_i
   logical, dimension(its:ite)        :: flgcld
   real                               :: temp
   real                               :: holdc, holdci
   real, dimension(its:ite,kts:kte)   :: vt2g
   double precision                   :: coeres, acrfac, vt2r, vt2s,vt2i,      &
                                         pfrzdtr, nfrzdtr, pfrzdtc, nfrzdtc 
   real                               :: factor, source, value, supice,xlwork2

   real                               :: cpmcal, xlcal, lamdac, diffus, &
                                         viscos, xka, venfac, conden, diffac,  &
                                         x, y, z, a, b, c, d, e,               &
                                         ndt, qdt, holdrr, holdrs, holdrg,     &
                                         supcol, supcolt, pvt, supsat,         &
                                         dtcld, xmi, eacsi, satdt, qimax,      &
                                         diameter, xni0, roqi0,                &
                                         fallsum, fallsum_qsi, fallsum_qg,     &
                                         egs, eacgi, coecol,                   &
                                         taucon, lencon, lenconcr,             &
                                         xlf,                                  &
                                         alpha1,alpha2, delta2, delta3
!
   integer                            :: i, j, k, mstepmax,mstepmax_i,         &
                                         iprt, latd, lond, loop, loops, ifsat, &
                                         n, idim, kdim
!
! Temporaries used for inlining fpvs function
!
   real                               :: dldti, xb, xai, tr, xbi, xa, hvap,    &
                                         cvap, hsub, dldt, ttp
!-------------------------------------------------------------------------------
! 20250125 yhlee
! Evapotaion tunning parameter and ncmin
!   real,parameter                      :: fac_evap = 1.2
   real,parameter                      :: fac_evap = 1.0
! Nc minimum for conversion processes
   real                                :: ncmin
! ------------------------------------------------------------------------------
!
!
! compute internal functions
!
   cpmcal(x) = cpd*(1.-max(x,qmin))+max(x,qmin)*cpv
   xlcal(x) = xlv0-xlv1*(x-t0c)
!
! size distributions: (x=mixing ratio, y=air density):
! valid for mixing ratio > 1.e-9 kg/kg.
!
! optimizatin : A**B => exp(log(A)*(B)) 
!
!   lamdac(x,y,z)= exp(log(((pidnc*z)/(x*y)))*((.33333333)))
! revised
   lamdac(x,y,z)= exp(log(((pidnc*z)/(x*y)))*(1./dmc))
!
! diffus: diffusion coefficient of the water vapor
! viscos: kinematic viscosity(m2s-1)
!
   diffus(x,y) = 8.794e-5 * exp(log(x)*(1.81)) / y   ! 8.794e-5*x**1.81/y
   viscos(x,y) = 1.496e-6 * (x*sqrt(x)) /(x+120.)/y  ! 1.496e-6*x**1.5/(x+120.)/y
   xka(x,y)    = 1.414e3*viscos(x,y)*y
   diffac(a,b,c,d,e) = d*a*a/(xka(c,d)*rv*c*c)+1./(e*diffus(c,b))
   venfac(a,b,c) = exp(log((viscos(b,c)/diffus(b,a)))*((.3333333)))            &
                   /sqrt(viscos(b,c))*sqrt(sqrt(den0/c))
   conden(a,b,c,d,e) = (max(b,qmin)-c)/(1.+d*d/(rv*e)*c/(a*a))
!
   idim = ite-its+1
   kdim = kte-kts+1
!
   kte_in = kte
!
!  paddint 0 for negative values generated by dynamics
!
   do k = kts, kte
     do i = its, ite
       qci(i,k,1) = max(qci(i,k,1),0.0)
       qrs(i,k,1) = max(qrs(i,k,1),0.0)
       qci(i,k,2) = max(qci(i,k,2),0.0)
       qrs(i,k,2) = max(qrs(i,k,2),0.0)
       qrs(i,k,3) = max(qrs(i,k,3),0.0)
       nrs(i,k,1) = max(nrs(i,k,1),0.0)
       nrs(i,k,2) = max(nrs(i,k,2),0.0)
       nrs(i,k,3) = max(nrs(i,k,3),0.0)
       nci(i,k,1) = max(nci(i,k,1),0.0)
       nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
!ADD UPPER BOUND ON ICE NUMBER
!TO PREVENT VERY LARGE ICE NUMBER DUE TO HOMOGENEOUS FREEZING OF DROPLETS,
       nci(i,k,2) = min(max(nci(i,k,2),0.0),1.0e6)
       rhox(i,k) = max(rhox(i,k),0.0)
       brs(i,k) = max(brs(i,k),0.0)
     enddo
   enddo
! imsi
   do k = kts,kte
     do i = its,ite
       dend(i,k) = den(i,k)
     enddo
   enddo
!
! 20250205 ncmin setting
! yhlee start 
   do i = its,ite
     if(slmsk(i).eq.2) then ! land
        ncmin = ncmin_sea
     else
       ncmin = ncmin_land
     endif
   enddo
! yhlee end


!
!  latent heat for phase changes and heat capacity. neglect the
!  changes during microphysical process calculation
!  emanuel(1994)
!
   do k = kts,kte_in
     do i = its,ite
       cpm(i,k) = cpmcal(q(i,k))
       xl(i,k) = xlcal(t(i,k))
     enddo
   enddo
!
   qcr(:,:) = 0.0
   do i = its,ite
     if(slmsk(i).eq.2) then      ! water
       qcr(i,:) = qc0
     else
       qcr(i,:) = qc1
     endif
   enddo
!
   do k = kts,kte
     do i = its,ite
       delz_tmp(i,k) = delz(i,k)
       den_tmp(i,k) = den(i,k)
     enddo
   enddo
!
! initialize the surface rain, snow, graupel
!
   do i = its,ite
     rainncv(i) = 0.
     if(present(snowncv) .and. present(snow)) snowncv(i) = 0.
     if(present (graupelncv) .and. present(graupel)) graupelncv(i) = 0.
     sr(i) = 0.
!
! new local array to catch step snow and graupel
!
     tstepsnow(i) = 0.
     tstepgraup(i) = 0.
   enddo
!
! compute the minor time steps.
!
   loops = max(nint(delt/dtcldcr),1)
   dtcld = delt/loops
   if(delt.le.dtcldcr) dtcld = delt
!
   do loop = 1,loops
!
! initialize the large scale variables
!
     do i = its,ite
       mstep(i) = 1
       mstep_i(i) = 1
       mnstep(i) = 1
       flgcld(i) = .true.
     enddo
!
     do k = kts, kte
       call VREC( tvec1(its), den(its,k), ite-its+1)
       do i = its, ite
         tvec1(i) = tvec1(i)*den0
       enddo
       call VSQRT( denfac(its,k), tvec1(its), ite-its+1)
     enddo
!
! Inline expansion for fpvs
!   qs(i,k,1) = fpvs(t(i,k),0,rd,rv,cpv,cliq,cice,xlv0,xls,psat,t0c)
!   qs(i,k,2) = fpvs(t(i,k),1,rd,rv,cpv,cliq,cice,xlv0,xls,psat,t0c)
!
     hsub = xls
     hvap = xlv0
     cvap = cpv
     ttp = t0c+0.01
     dldt = cvap-cliq
     xa = -dldt/rv
     xb = xa+hvap/(rv*ttp)
     dldti = cvap-cice
     xai = -dldti/rv
     xbi = xai+hsub/(rv*ttp)
!
     do k = kts,kte_in
       do i = its,ite
         tr = ttp/t(i,k)
         qs(i,k,1) = psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
         qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
         qs(i,k,1) = ep2*qs(i,k,1)/(p(i,k)-qs(i,k,1))
         qs(i,k,1) = max(qs(i,k,1),qmin)
         rh(i,k,1) = max(q(i,k)/qs(i,k,1),qmin)
         sw(i,k) = (rh(i,k,1)-1.)*100.
         tr=ttp/t(i,k)
         if(t(i,k).lt.ttp) then
           qs(i,k,2) = psat*exp(log(tr)*(xai))*exp(xbi*(1.-tr))
         else
           qs(i,k,2) = psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
         endif
         qs(i,k,2) = min(qs(i,k,2),0.99*p(i,k))
         qs(i,k,2) = ep2*qs(i,k,2)/(p(i,k)-qs(i,k,2))
         qs(i,k,2) = max(qs(i,k,2),qmin)
         rh(i,k,2) = max(q(i,k)/qs(i,k,2),qmin)
       enddo
     enddo
!
!----------------------------------------------------------------
!     initialize the variables for microphysical physics
!
!
      do k = kts, kte
        do i = its, ite
          bvtg(i,k) =0.
          rslopegbmax(i,k) =0.
          dgbgmug1(i,k) =0.
          bvtg1(i,k) =0.
          bvtg2(i,k) =0.
          bvtg3(i,k) =0.
          bvtg4(i,k) =0.
          g1pdgbgmg(i,k) =0.
          g1pbg(i,k) =0.
          g3pbg(i,k) =0.
          g4pbg(i,k) =0.
          g5pbgo2(i,k) =0.
          cmg(i,k) =0.
          pidn0g(i,k) =0.
          avtg(i,k) =0.
          pvtg(i,k) =0.
          precg2(i,k) =0.
          rhox(i,k) =0.
          biacr(i,k) =0.
          baacw(i,k) =0.
          bsacr(i,k) =0.
          braci(i,k) =0.
          bracs(i,k) =0.
          bsaci(i,k) =0.
          bsaut(i,k) =0.
          bgaci(i,k) =0.
          bgacr(i,k) =0.
          bgacs(i,k) =0.
          bgaut(i,k) =0.
          bgdep(i,k) =0.
          bsdep(i,k) =0.
          bsevp(i,k) =0.
          bseml(i,k) =0.
          bgevp(i,k) =0.
          bgeml(i,k) =0.
          prevp(i,k) = 0.
          psdep(i,k) = 0.
          pgdep(i,k) = 0.
          praut(i,k) = 0.
          psaut(i,k) = 0.
          nsaut(i,k) = 0.
          pgaut(i,k) = 0.
          pracw(i,k) = 0.
          praci(i,k) = 0.
          piacr(i,k) = 0.
          psaci(i,k) = 0.
          psacw(i,k) = 0.
          pracs(i,k) = 0.
          psacr(i,k) = 0.
          pgacw(i,k) = 0.
          paacw(i,k) = 0.
          pgaci(i,k) = 0.
          pgacr(i,k) = 0.
          pgacs(i,k) = 0.
          pigen(i,k) = 0.
          pidep(i,k) = 0.
          nisub(i,k) = 0.
          niacw(i,k) = 0.
          piacw(i,k) = 0.
          pcond(i,k) = 0.
          psmlt(i,k) = 0.
          pgmlt(i,k) = 0.
          pseml(i,k) = 0.
          pgeml(i,k) = 0.
          psevp(i,k) = 0.
          pgevp(i,k) = 0.
          pcact(i,k) = 0.
          falk(i,k,1) = 0.
          falk(i,k,2) = 0.
          falk(i,k,3) = 0.
          fall(i,k,1) = 0.
          fall(i,k,2) = 0.
          fall(i,k,3) = 0.
          falkc(i,k) = 0.
          falln(i,k,1) =0.
          falln(i,k,2) =0.
          falkn(i,k,1) =0.
          falkn(i,k,2) =0.
          falkb(i,k) = 0.
          fallb(i,k) = 0.
          xni(i,k) = 1.e3
          nsacw(i,k) = 0.
          ngacw(i,k) = 0.
          naacw(i,k) = 0.
          niacr(i,k) = 0.
          nsacr(i,k) = 0.
          ngacr(i,k) = 0.
          nseml(i,k) = 0.
          ngeml(i,k) = 0.
          nracw(i,k) = 0.
          nccol(i,k) = 0.
          nrcol(i,k) = 0.
          ncact(i,k) = 0.
          nraut(i,k) = 0.
          ncevp(i,k) = 0.
          falk(i,k,4) = 0.
          fall(i,k,4) = 0.
          pmulcs(i,k) =0.
          pmulcg(i,k) =0.
          pmulrs(i,k) =0.
          pmulrg(i,k) =0.
          nmulcs(i,k) =0.
          nmulcg(i,k) =0.
          nmulrs(i,k) =0.
          nmulrg(i,k) =0.
          nraci(i,k) = 0.
          nsaci(i,k) = 0.
          ngaci(i,k) = 0.
          nracs(i,k) = 0.
          ninud(i,k) = 0.
          pinud(i,k) = 0.
        enddo
      enddo
!
      do k = kts, kte
        do i = its, ite
          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecmu(i,k) = rslopecmmax
            rslopecd(i,k) = rslopecdmax  
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),den(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) =DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif
        enddo
      enddo
!----------------------------------------------------------------
!     compute the fallout term:
!     first, vertical terminal velosity for minor loops
!----------------------------------------------------------------
      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)
!---------------------------------------------------------------
! vt update for qr and nr
!---------------------------------------------------------------
      mstepmax = 1
      mstepmax_i = 1
      numdt = 1
      numdt_i = 1
      do k = kte, kts, -1
        do i = its, ite
          work1(i,k,1) = work1(i,k,1)/delz(i,k)
          work1(i,k,4) = work1(i,k,4)/delz(i,k)
          workn(i,k,1) = workn(i,k,1)/delz(i,k)
          workn(i,k,2) = workn(i,k,2)/delz(i,k)
          work1(i,k,2) = work1(i,k,2)/delz(i,k)
          work1(i,k,3) = work1(i,k,3)/delz(i,k)
          numdt(i)=max(nint(max(work1(i,k,1),workn(i,k,1),work1(i,k,2),work1(i,k,3))*dtcld+.5),1)
          numdt_i(i) = max(nint(max(work1(i,k,4),workn(i,k,2))*dtcld+.5),1)
          if(numdt(i).ge.mstep(i)) mstep(i) = numdt(i)
          if(numdt_i(i).ge.mstep_i(i)) mstep_i(i) = numdt_i(i)
        enddo
      enddo

      do i = its, ite
        if(mstepmax.le.mstep(i)) mstepmax = mstep(i)
        if(mstepmax_i.le.mstep_i(i)) mstepmax_i = mstep_i(i)
      enddo

      do n = 1, mstepmax
        k = kte
        do i = its, ite
         if(n.le.mstep(i)) then
           falk(i,k,1) = dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)
           falkn(i,k,1) = nrs(i,k,1)*workn(i,k,1)/mstep(i)
           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
           falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)
           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)
           falkb(i,k) = dend(i,k)*brs(i,k)*work1(i,k,3)/mstep(i)
           fallb(i,k) = fallb(i,k)+falkb(i,k)
           brs(i,k) = max(brs(i,k)-falkb(i,k)*dtcld/dend(i,k),0.)
           falk(i,k,2) = dend(i,k)*qrs(i,k,2)*work1(i,k,2)/mstep(i)
           fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
           qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)
           falk(i,k,3) = dend(i,k)*qrs(i,k,3)*work1(i,k,3)/mstep(i)
           fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
           qrs(i,k,3) = max(qrs(i,k,3)-falk(i,k,3)*dtcld/dend(i,k),0.)
         endif
       enddo
!
       do k = kte_in-1,kts,-1
         do i = its,ite
           if(n.le.mstep(i)) then
             falk(i,k,1) = dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep(i)
             falkn(i,k,1) = nrs(i,k,1)*workn(i,k,1)/mstep(i)
             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
             dqr(i,k) = min(falk(i,k,1)*dtcld/dend(i,k),qrs(i,k,1))
             dqr(i,k+1) = min(falk(i,k+1,1)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qrs(i,k+1,1))
             falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
             dnr(i,k) = min(falkn(i,k,1)*dtcld,nrs(i,k,1))
             dnr(i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld,        &
                          nrs(i,k+1,1))
             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)
             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)
             falkb(i,k) = dend(i,k)*brs(i,k)*work1(i,k,3)/mstep(i)
             fallb(i,k) = fallb(i,k)+falkb(i,k)
             dbg(i,k) = min(falkb(i,k)*dtcld/dend(i,k),brs(i,k))
             dbg(i,k+1) = min(falkb(i,k+1)*delz(i,k+1)/delz(i,k)&
                          *dtcld/dend(i,k),brs(i,k+1))
             brs(i,k) = max(brs(i,k)-dbg(i,k)+dbg(i,k+1),0.)
             falk(i,k,2) = dend(i,k)*qrs(i,k,2)*work1(i,k,2)/mstep(i)
             fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
             dqs(i,k) = min(falk(i,k,2)*dtcld/dend(i,k),qrs(i,k,2))
             dqs(i,k+1) = min(falk(i,k+1,2)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qrs(i,k+1,2))
             qrs(i,k,2) = max(qrs(i,k,2)-dqs(i,k)+dqs(i,k+1),0.)
             falk(i,k,3) = dend(i,k)*qrs(i,k,3)*work1(i,k,3)/mstep(i)
             fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
             dqg(i,k) = min(falk(i,k,3)*dtcld/dend(i,k),qrs(i,k,3))
             dqg(i,k+1) = min(falk(i,k+1,3)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qrs(i,k+1,3))
             qrs(i,k,3) = max(qrs(i,k,3)-dqg(i,k)+dqg(i,k+1),0.)
            endif
          enddo
        enddo

        do k = kts, kte
          do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
          enddo
        enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)

        do k = kte, kts, -1
          do i = its, ite
            work1(i,k,1) = work1(i,k,1)/delz(i,k)
            workn(i,k,1) = workn(i,k,1)/delz(i,k)
            work1(i,k,2) = work1(i,k,2)/delz(i,k)
            work1(i,k,3) = work1(i,k,3)/delz(i,k)
          enddo
        enddo
      enddo      ! do n = 1, mstepmax

!---------------------------------------------------------------
! vt update for qi and ni
!---------------------------------------------------------------
      do n = 1, mstepmax_i
        k = kte
        do i = its, ite
         if(n.le.mstep_i(i)) then
           falk(i,k,4) = dend(i,k)*qci(i,k,2)*work1(i,k,4)/mstep_i(i)
           falkn(i,k,2) = nci(i,k,2)*workn(i,k,2)/mstep_i(i)
           fall(i,k,4) = fall(i,k,4)+falk(i,k,4)
           falln(i,k,2) = falln(i,k,2)+falkn(i,k,2)
           qci(i,k,2) = max(qci(i,k,2)-falk(i,k,4)*dtcld/dend(i,k),0.)
           nci(i,k,2) = max(nci(i,k,2)-falkn(i,k,2)*dtcld,0.)
         endif
       enddo


       do k = kte_in-1,kts,-1
         do i = its,ite
           if(n.le.mstep_i(i)) then
             falk(i,k,4) = dend(i,k)*qci(i,k,2)*work1(i,k,4)/mstep_i(i)
             falkn(i,k,2) = nci(i,k,2)*workn(i,k,2)/mstep_i(i)
             fall(i,k,4) = fall(i,k,4)+falk(i,k,4)
             dqi(i,k) = min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))
             dqi(i,k+1) = min(falk(i,k+1,4)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qci(i,k+1,2))
             falln(i,k,2) = falln(i,k,2)+falkn(i,k,2)
             dni(i,k) = min(falkn(i,k,2)*dtcld,nci(i,k,2))
             dni(i,k+1) = min(falkn(i,k+1,2)*delz(i,k+1)/delz(i,k)*dtcld,      &
                          nci(i,k+1,2))
             nci(i,k,2) = max(nci(i,k,2)-dni(i,k)+dni(i,k+1),0.)
             qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)
            endif
          enddo
        enddo 

        do k = kts, kte
          do i = its, ite
            qrs_tmp(i,k,1) = qrs(i,k,1)
            qrs_tmp(i,k,2) = qrs(i,k,2)
            qrs_tmp(i,k,3) = qrs(i,k,3)
            qci_tmp(i,k) = qci(i,k,2)
            nci_tmp(i,k) = nci(i,k,2)
            nrs_tmp(i,k) = nrs(i,k,1)
          enddo
        enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)

       do k = kte, kts, -1
         do i = its, ite
            work1(i,k,4) = work1(i,k,4)/delz(i,k)
            workn(i,k,2) = workn(i,k,2)/delz(i,k)
         enddo
       enddo
      enddo ! do n = 1, mstepmax_i 
!
      do k = kte, kts, -1
        do i = its, ite
          supcol = t0c-t(i,k)
          if(supcol.lt.0.) xlf = xlf0
          n0so(i,k) = (n0s)/g1pms/(rslopemu(i,k,2)) 
          n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))  
          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          if(t(i,k).gt.t0c) then
!---------------------------------------------------------------
! psmlt: melting of snow [HL A33] [RH83 A25]
!       (T>T0: QS->QR)
!---------------------------------------------------------------
            work2(i,k) = venfac(p(i,k),t(i,k),den(i,k))
            if(qrs(i,k,2).gt.0.) then
! revised
              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2))          &
                       *rslopemu(i,k,2)
              psmlt(i,k) =(xka(t(i,k),den(i,k)))/xlf*(t0c-t(i,k))*n0sfac(i,k)       &
                         *pi/2.*((precs1)*n0so(i,k)*rslope2(i,k,2)*rslopemu(i,k,2)  &
                         +(precs2)*n0so(i,k)*work2(i,k)*coeres)/den(i,k)
              psmlt(i,k) = min(max(psmlt(i,k)*dtcld,-qrs(i,k,2)),0.)
!-------------------------------------------------------------------
! nsmlt: melting of snow [LH A27]
!       (T>T0: ->NR)
!-------------------------------------------------------------------
              if(qrs(i,k,2).gt.qcrmin) then
                sfac = (rslope(i,k,2))*n0so(i,k)*n0sfac(i,k)/qrs(i,k,2)
                nrs(i,k,1) = nrs(i,k,1) - sfac*psmlt(i,k)
              endif
              qrs(i,k,2) = qrs(i,k,2) + psmlt(i,k)
              qrs(i,k,1) = qrs(i,k,1) - psmlt(i,k)
              t(i,k) = t(i,k) + xlf/cpm(i,k)*psmlt(i,k)
            endif
!---------------------------------------------------------------
! pgmlt: melting of graupel [HL A23]  [LFO 47]
!       (T>T0: QG->QR)
!---------------------------------------------------------------
            if(qrs(i,k,3).gt.0.) then
! revised 
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &
                       *rslopemu(i,k,3)
              pgmlt(i,k) = (xka(t(i,k),den(i,k)))/xlf*(t0c-t(i,k))                   &
                           *pi/2.*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3) &
                           +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/den(i,k)
              pgmlt(i,k) = min(max(pgmlt(i,k)*dtcld,-qrs(i,k,3)),0.)
!-------------------------------------------------------------------
! ngmlt: melting of graupel [LH A28]
!       (T>T0: ->NR)
!-------------------------------------------------------------------
              if(qrs(i,k,3).gt.qcrmin) then
                gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
                nrs(i,k,1) = nrs(i,k,1) - gfac*pgmlt(i,k)
              endif
              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)
              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)
              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)
              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))
            endif
!---------------------------------------------------------------
! pimlt: instantaneous melting of cloud ice [HL A47] [RH83 A28]
!       (T>T0: QI->QC)
! nimlt: instantaneous melting of cloud ice  [LH A18]
!       (T>T0:NI->NC)
!---------------------------------------------------------------
              if(qci(i,k,2).gt.0) then
                  qci(i,k,1) = qci(i,k,1) + qci(i,k,2)
                  nci(i,k,1) = nci(i,k,1) + nci(i,k,2)
            t(i,k) = t(i,k) - xlf/cpm(i,k)*qci(i,k,2)
            qci(i,k,2) = 0.
            nci(i,k,2) = 0.
           endif
          endif  !supcol 
        enddo
      enddo
!----------------------------------------------------------------
!      rain (unit is mm/sec;kgm-2s-1: /1000*delt ===> m)==> mm for wrf
!
      do i = its, ite
        fallsum = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)
        fallsum_qsi = fall(i,kts,2)+fall(i,kts,4)
        fallsum_qg = fall(i,kts,3)
        if(fallsum.gt.0.) then
          rainncv(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rainncv(i)
          rain(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rain(i)
        endif
        If(fallsum_qsi.gt.0.) then
          tstepsnow(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + tstepsnow(i)
          IF( PRESENT (snowncv) .AND. PRESENT (snow)) THEN
            snowncv(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + snowncv(i)     
            snow(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + snow(i)
          ENDIF
        ENDIF
        IF(fallsum_qg.gt.0.) then
          tstepgraup(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000.              &
                            + tstepgraup(i)
          IF( PRESENT (graupelncv) .AND. PRESENT (graupel)) THEN
            graupelncv(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000.            &  
                            + graupelncv(i)
            graupel(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000. + graupel(i)
          ENDIF
        ENDIF
        IF ( PRESENT (snowncv)) THEN
          if(fallsum.gt.0.)sr(i)=(snowncv(i) + graupelncv(i))/(rainncv(i)+1.e-12)
        ELSE
          if(fallsum.gt.0.)sr(i)=(tstepsnow(i) + tstepgraup(i))/(rainncv(i)+1.e-12)
        ENDIF
      enddo
!
! added by sunny
      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)
!
      do k = kts, kte
        do i = its, ite
          supcol = t0c-t(i,k)
          xlf = xls-xl(i,k)
          if(supcol.lt.0.) xlf = xlf0
!---------------------------------------------------------------
! pihmf: homogeneous  of cloud water below -40c [HL A45]
!        (T<-40C: QC->QI)
!---------------------------------------------------------------
          if(supcol.gt.40. .and. qci(i,k,1).gt.0.) then
            qci(i,k,2) = qci(i,k,2) + qci(i,k,1)
            nci(i,k,2) = nci(i,k,2) + nci(i,k,1)
!---------------------------------------------------------------
! nihmf: homogeneous  of cloud water below -40c [LH A17]
!        (T<-40C: NC->) 
!---------------------------------------------------------------
            t(i,k) = t(i,k) + xlf/cpm(i,k)*qci(i,k,1)
            qci(i,k,1) = 0.
            nci(i,k,1) = 0.
          endif

          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopecmu(i,k) = rslopecmmax
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecd(i,k) = rslopecdmax  
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),den(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif
          n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi) 
!
          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(den(i,k)*qrs(i,k,1))))*(1./dmr))
            n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(den(i,k)*qci(i,k,1))))*(1./dmc))
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            endif
          endif
          if(qci(i,k,2) .ge. 1.e-14 ) then
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
          endif
!---------------------------------------------------------------
! pinuc: contact freezing  of cloud water to cloud ice [HL A44]
!        (-2>T, QC->QI)
!---------------------------------------------------------------
          if(supcol.gt.2. .and. qci(i,k,1).gt.qmin) then  
            supcolt=min(supcol,70.)
            Nic = exp(-2.80+0.262*(supcolt))*1000 ! meyers curve
            ele1 = 7.37*t(i,k)/(288.*10.*p(i,k))/100 !mean free path
            ele2 = 4.*pi*1.38E-23/(6.*pi*Rcn) ! 1.38E-23 Boltzmann constant 
            !diffusivity of aerosol[m2s-1]
            difa(i,k) = ele2*t(i,k)*(1.+ele1/Rcn)/(viscos(t(i,k),den(i,k))*den(i,k))
            pinuc = min((cmc)*difa(i,k)*2.*pi*Nic*n0c(i,k)/den(i,k)/(muc+1) &
                *g4pmc*rslopecmu(i,k)*rslopec3(i,k)*rslopec2(i,k)*dtcld,qci(i,k,1))
!---------------------------------------------------------------
! ninuc: heterogeneous  of cloud water [HL A44]
!        (-4>T>-40C: NC->NI)
!---------------------------------------------------------------
            if (nci(i,k,1) .gt. ncmin) then
              ninuc = min((difa(i,k))*2.*pi*Nic*n0c(i,k)/(muc+1) &
                      *g1pmc*rslopecmu(i,k)*rslopec2(i,k)*dtcld,nci(i,k,1))
              nci(i,k,1) = nci(i,k,1)-(ninuc)
              nci(i,k,2) = nci(i,k,2)+(ninuc)
            endif
            qci(i,k,1) = qci(i,k,1)-(pinuc)
            qci(i,k,2) = qci(i,k,2)+(pinuc)
            t(i,k) = t(i,k) + xlf/cpm(i,k)*pinuc 
          endif
!---------------------------------------------------------------
! pinui: immersion freezing of cloud water [HL A44]
!        (T0>T>-40C: QC->QI) (old:pihtf)
!---------------------------------------------------------------
          if(supcol.gt.0. .and. qci(i,k,1).gt.qmin) then
            supcolt=min(supcol,70.)
            pfrzdtc = min((cmc)*cmc*pfrz1*n0c(i,k)/den(i,k)/denr/(muc+1)       &
                    *(exp(pfrz2*supcolt)-1.)*g1p2dcomuc1*rslopecmu(i,k)        &
                    *rslopecd(i,k)*rslopecd(i,k)*rslopec(i,k)*dtcld            &  
                !    *(exp(pfrz2*supcolt)-1.)*2.*rslopecmu(i,k)                & 
                !    *rslopecmu(i,k)*rslopecmu(i,k)*rslopec3(i,k)*dtcld         &
                     ,qci(i,k,1))
!---------------------------------------------------------------
! ninui: heterogeneous  of cloud water [LH A16]
!         (T0>T>-40C: NC->) 
!---------------------------------------------------------------
            if(nci(i,k,1).gt.ncmin) then
!revised
              nfrzdtc = min((cmc)*pfrz1*n0c(i,k)/denr/(muc+1)        &
                       *(exp(pfrz2*supcolt)-1.)*g1pdcomuc1*rslopecmu(i,k)       &  
                       *rslopec(i,k)*rslopecd(i,k)*dtcld,nci(i,k,1))
!                      *(exp(pfrz2*supcolt)-1.)*rslopecmu(i,k)       &
!                      *rslopecmu(i,k)*rslopec2(i,k)*dtcld,nci(i,k,1))
              nci(i,k,1) = nci(i,k,1)-(nfrzdtc) 
              nci(i,k,2) = nci(i,k,2)+(nfrzdtc)
            endif
            qci(i,k,1) = qci(i,k,1)-(pfrzdtc)
            qci(i,k,2) = qci(i,k,2)+(pfrzdtc)
            t(i,k) = t(i,k) + xlf/cpm(i,k)*(pfrzdtc)
          endif
!---------------------------------------------------------------
! pgfrz:  freezing of rain water [HL A20] [LFO 45]
!        (T<T0, QR->QG)
!---------------------------------------------------------------
          if(supcol.gt.0. .and. qrs(i,k,1).gt.0.) then
            supcolt=min(supcol,70.)
            pfrzdtr = min((cmr)*cmr*pfrz1*n0r(i,k)/den(i,k)/denr          &
                  *(exp(pfrz2*supcolt)-1.)*rsloped(i,k,1)*rsloped(i,k,1)       & 
                  *rslopemu(i,k,1)*rslope(i,k,1)*g1p2drmr*dtcld,qrs(i,k,1))        
!---------------------------------------------------------------
! ngfrz: freezing of rain water [LH A26]
!        (T<T0, NR-> ) 
!---------------------------------------------------------------
            if(nrs(i,k,1).gt.nrmin) then
              nfrzdtr = min((cmr)/denr*pfrz1*n0r(i,k)*(exp(pfrz2*supcolt)-1.)     &
                       *g1pdrmr*rslope(i,k,1)*rsloped(i,k,1)*rslopemu(i,k,1) &
                       *dtcld, nrs(i,k,1)) 
              nrs(i,k,1) = nrs(i,k,1) - nfrzdtr
            endif
            qrs(i,k,3) = qrs(i,k,3) + pfrzdtr
            brs(i,k) = brs(i,k) + (pfrzdtr/denr)
            t(i,k) = t(i,k) + xlf/cpm(i,k)*pfrzdtr
            qrs(i,k,1) = qrs(i,k,1) - pfrzdtr
          endif
        enddo
      enddo
!
      do k = kts, kte
        do i = its, ite
          nrs(i,k,1) = max(nrs(i,k,1),0.0)
          nci(i,k,1) = max(nci(i,k,1),0.0)
          nci(i,k,2) = max(nci(i,k,2),0.0)
        enddo
      enddo
!
!----------------------------------------------------------------
!     update the slope parameters for microphysics computation
!
      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)

      do k = kts, kte
        do i = its, ite
!-----------------------------------------------------------------
! compute the mean-volume drop diameter                  [LH A10] 
! for raindrop distribution                          
!-----------------------------------------------------------------
!
          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin) then
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecmu(i,k) = rslopecmmax
            rslopecd(i,k) = rslopecdmax 
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),den(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif
! sunny
! error fix
          n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi)
          n0so(i,k) = (n0s)/g1pms/(rslopemu(i,k,2))
          n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))
!
          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(den(i,k)*qrs(i,k,1))))*(1./dmr))
            n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(den(i,k)*qci(i,k,1))))*(1./dmc))
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            endif
          endif
          if(qci(i,k,2).ge. 1.e-14 ) then
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*(lamdi_tmp(i,k)**dmi)/pidni
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
          endif
!--------------------------------------------------------------------
! compute the mean-volume drop diameter                   [LH A7]
! for cloud-droplet distribution
!--------------------------------------------------------------------
          avedia(i,k,1) = rslopec(i,k)*(g3pmc)**(1./3.)
          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))
          avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))
          sigma(i,k,1) = rslopec(i,k)*(g6pmc-g3pmc*g3pmc)**(1./6.)
        enddo
      enddo
!
      do k = kts, kte
        do i = its, ite
          work1(i,k,1) = diffac(xl(i,k),p(i,k),t(i,k),den(i,k),qs(i,k,1))
          work1(i,k,2) = diffac(xls,p(i,k),t(i,k),den(i,k),qs(i,k,2))
          work2(i,k) = venfac(p(i,k),t(i,k),den(i,k))
        enddo
      enddo
!
!===============================================================
!
! warm rain processes
!
! - follows the double-moment processes in Lim and Hong
!
!===============================================================
!
      do k = kts, kte
        do i = its, ite
          supsat = max(q(i,k),qmin)-qs(i,k,1)
          satdt = supsat/dtcld
!---------------------------------------------------------------
! praut: auto conversion rate from cloud to rain  [LH 9] [CP 17]
!        (QC->QR)
!--------------------------------------------------------------
!         lencon  = 2.7e-2*den(i,k)*qci(i,k,1)*(1.e20/16.*rslopec2(i,k)         &
!                  *rslopec2(i,k)-0.4)
         lencon  = 2.7e-2*den(i,k)*qci(i,k,1)*(1.e20/16.*avedia(i,k,1) &
                  *(sigma(i,k,1)**3)-0.4)
         lenconcr = max(1.2*lencon, qcrmin)
         if(qci(i,k,1).gt.qcr(i,k) .and. nci(i,k,1).gt.ncmin) then
           praut(i,k) = (qck1)*qci(i,k,1)**(7./3.)*nci(i,k,1)**(-1./3.)
           praut(i,k) = min(praut(i,k),qci(i,k,1)/dtcld)
!----------------------------------------------------------------------
! nraut: auto conversion rate from cloud to rain [LH A6] [CP 18 & 19]
!        (NC->NR)
!------------------------------------------------------------------------
           nraut(i,k) = (3.5e9)*den(i,k)*praut(i,k)
           if(qrs(i,k,1).gt.lenconcr)                                           &
           nraut(i,k) = nrs(i,k,1)/qrs(i,k,1)*praut(i,k)
           nraut(i,k) = min(nraut(i,k),nci(i,k,1)/dtcld)
         endif
!---------------------------------------------------------------
! pracw: accretion of cloud water by rain     [LH 10] [CP 22 & 23]
!        (QC->QR)
! nracw: accretion of cloud water by rain     [LH A9]
!        (NC->)
!---------------------------------------------------------------
          if(qrs(i,k,1).ge.lenconcr) then
            if(avedia(i,k,2).ge.di100) then
              nracw(i,k) = min((ncrk1)*nci(i,k,1)*nrs(i,k,1)                          &
                         *((rslopec3(i,k))*g3pmc +(rslope3(i,k,1))*(g4pmr/g1pmr))     &
                         ,nci(i,k,1)/dtcld)
              pracw(i,k) = min(((cmc)/den(i,k))*ncrk1*nci(i,k,1)                      &
                         *nrs(i,k,1)*rslopec3(i,k)*((rslopec3(i,k))*g6pmc             &
                         +(rslope3(i,k,1))*g3pmc*(g4pmr/g1pmr)),qci(i,k,1)/dtcld)
            else
              nracw(i,k) = min((ncrk2)*nci(i,k,1)*nrs(i,k,1)                          &
                         *((rslopec3(i,k))*rslopec3(i,k)*g6pmc                        &
                         +(rslope3(i,k,1))*rslope3(i,k,1))*(g7pmr/g1pmr)              &
                         ,nci(i,k,1)/dtcld)
              pracw(i,k) = min(((cmc)/den(i,k))*ncrk2*nci(i,k,1)                      &
                         *nrs(i,k,1)*rslopec3(i,k)*((rslopec3(i,k))*rslopec3(i,k)     &
                         *g9pmc+(rslope3(i,k,1))*rslope3(i,k,1)*g3pmc*(g7pmr/g1pmr))  &
                         ,qci(i,k,1)/dtcld)
            endif
          endif 
!----------------------------------------------------------------
! nccol: self collection of cloud water             [LH A8] [CP 24 & 25]     
!        (NC->)
!----------------------------------------------------------------
          if(avedia(i,k,1).ge.di100) then
!revised
            nccol(i,k) = (ncrk1)*nci(i,k,1)*nci(i,k,1)*rslopec3(i,k)     &
                         *g3pmc
          else
            nccol(i,k) = (ncrk2)*nci(i,k,1)*nci(i,k,1)*rslopec3(i,k)        &
                         *rslopec3(i,k)*g6pmc
          endif
!----------------------------------------------------------------
! nrcol: self collection of rain-drops and break-up [LH A21] [CP 24 & 25]
!        (NR->)
!----------------------------------------------------------------
          if(qrs(i,k,1).ge.lenconcr) then
            if(avedia(i,k,2).lt.di100) then
! revised
              nrcol(i,k) = (ncrk2)*nrs(i,k,1)*nrs(i,k,1)*rslope3(i,k,1) &
                          *rslope3(i,k,1)*(g7pmr/g1pmr)
            elseif(avedia(i,k,2).ge.di100 .and. avedia(i,k,2).lt.di600) then
              nrcol(i,k) = (ncrk1)*nrs(i,k,1)*nrs(i,k,1)*rslope3(i,k,1)&
                          *(g4pmr/g1pmr)
            elseif(avedia(i,k,2).ge.di600 .and. avedia(i,k,2).lt.di2000) then
              coecol = (-2.5e3)*eccbrk*(avedia(i,k,2)-di600)
              nrcol(i,k) = (exp(coecol))*ncrk1*nrs(i,k,1)*nrs(i,k,1) &
                         *rslope3(i,k,1)*(g4pmr/g1pmr)
            else
              nrcol(i,k) = (0.)
            endif
          endif
!---------------------------------------------------------------
! prevp: evaporation/condensation rate of rain   [HL A41]  
!        (QV->QR or QR->QV)
!---------------------------------------------------------------
          if(qrs(i,k,1).gt.0.) then
            coeres = (rslope2(i,k,1))*sqrt(rslope(i,k,1)*rslopeb(i,k,1))&
                     *rslopemu(i,k,1)
            prevp(i,k) = ((rh(i,k,1)-1.))*n0r(i,k)*(precr1*rslope2(i,k,1)&
                        *rslopemu(i,k,1)+(precr2)*work2(i,k)*coeres)/work1(i,k,1)
! 20250116 yhlee
            prevp(i,k) = fac_evap*prevp(i,k) ! added evaporation tunning parameter
!
            if(prevp(i,k).lt.0.) then
              prevp(i,k) = max(prevp(i,k),-(qrs(i,k,1))/dtcld)
              prevp(i,k) = max(prevp(i,k),(satdt)/2)
!----------------------------------------------------------------
! Nrevp: evaporation/condensation rate of rain   [LH A14] 
!        (NR->NCCN) 
!----------------------------------------------------------------
              if(prevp(i,k).eq.-qrs(i,k,1)/dtcld) then
                nci(i,k,3) = nci(i,k,3)+nrs(i,k,1)
                nrs(i,k,1) = 0.
              endif
            else
              prevp(i,k) = min(prevp(i,k),(satdt)/2)
            endif
          endif
        enddo
      enddo
!
!===============================================================
!
! cold rain processes
!
! - follows the revised ice microphysics processes in HDC
! - the processes same as in RH83 and RH84  and LFO behave
!   following ice crystal hapits defined in HDC, inclduing
!   intercept parameter for snow (n0s), ice crystal number
!   concentration (ni), ice nuclei number concentration
!   (n0i), ice diameter (d)
!
!===============================================================
!
      do k = kts, kte
        do i = its, ite
          supcol = t0c-t(i,k)
          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          supsat = max(q(i,k),qmin)-qs(i,k,2)
          satdt = supsat/dtcld
          ifsat = 0
!
          eacsi = exp(0.07*(-supcol))
          vt2i=DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          vt2r=DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
          vt2s=DBLE(pvts)*rslopeb(i,k,2)*denfac(i,k)
          vt2g(i,k)=DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)
          qsum(i,k) = max((qrs(i,k,2)+qrs(i,k,3)),1.e-15)
          if(supcol.gt.0.) then
!-------------------------------------------------------------
! praci: Accretion of cloud ice by rain [HL A15] [LFO 25]
!        (T<T0: QI->QR)
!-------------------------------------------------------------
          if(qci(i,k,2).gt.qmin .and. qrs(i,k,1).gt.qcrmin) then
! revised 
              acrfac=(g3pmr)*rslopemu(i,k,1)*rslope3(i,k,1)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
              +(2.)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
              +(g1pmr)*rslopemu(i,k,1)*rslope(i,k,1)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)
!
                praci(i,k)=(pi)*cmi*n0i(i,k)*n0r(i,k)*abs(vt2r-vt2i)/(4*den(i,k))*acrfac*eacri

                ! reduce collection efficiency (suggested by B. Wilt)
                praci(i,k) =praci(i,k)*min(max(0.0,qrs(i,k,1)/qci(i,k,2)),1.)**2
                praci(i,k) = min(praci(i,k),(qci(i,k,2))/dtcld)

!-------------------------------------------------------------
! piacr: Accretion of rain by cloud ice [HL A19] [LFO 26]
!        (T<T0: QR->QS or QR->QG)
!-------------------------------------------------------------
! revised 
             acrfac=(g3pmi)*rslopemu(i,k,4)*rslope3(i,k,4)*g1pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)&
              +(2.)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*g2pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)&
              +(g1pmi)*rslopemu(i,k,4)*rslope(i,k,4)*g3pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)
!
                piacr(i,k)=(pi)*cmr*n0i(i,k)*n0r(i,k)*abs(vt2i-vt2r)/(4*den(i,k))*acrfac*eacir

              ! reduce collection efficiency (suggested by B. Wilt)
              piacr(i,k) = piacr(i,k)*min(max(0.0,qci(i,k,2)/qrs(i,k,1)),1.)**2
              piacr(i,k) = min(piacr(i,k),(qrs(i,k,1))/dtcld)
        endif
!-------------------------------------------------------------
! psaci: Accretion of cloud ice by snow [HDC 10]
!        (T<T0: QI->QS)
!-------------------------------------------------------------
            if(qrs(i,k,2).gt.qcrmin .and. qci(i,k,2).gt.qmin) then
               acrfac=(g3pms)*rslopemu(i,k,2)*rslope3(i,k,2)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pms*rslopemu(i,k,2)*rslope2(i,k,2)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pms)*rslopemu(i,k,2)*rslope(i,k,2)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)
!
                psaci(i,k)=(pi)*cmi*n0i(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2i)/(4*den(i,k))*acrfac*eacsi
                psaci(i,k)=psaci(i,k)*min(max(0.0,qrs(i,k,2)/qci(i,k,2)),1.)**2
                psaci(i,k) = min(psaci(i,k),qci(i,k,2)/dtcld)
            endif
!-------------------------------------------------------------
! pgaci: Accretion of cloud ice by graupel [HL A17] [LFO 41]
!        (T<T0: QI->QG)
!-------------------------------------------------------------
            if(qrs(i,k,3).gt.qcrmin .and. qci(i,k,2).gt.qmin) then
              eacgi = exp(0.07*(-supcol))
                acrfac=(g3pmg)*rslopemu(i,k,3)*rslope3(i,k,3)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmg*rslopemu(i,k,3)*rslope2(i,k,3)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmg)*rslopemu(i,k,3)*rslope(i,k,3)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)

                pgaci(i,k)=(pi)*cmi*n0i(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2i)/(4*den(i,k))*acrfac*eacgi
                pgaci(i,k)=pgaci(i,k)*min(max(0.0,qrs(i,k,3)/qci(i,k,2)),1.)**2
                pgaci(i,k) = min(pgaci(i,k),qci(i,k,2)/dtcld)
            endif
         endif
!-------------------------------------------------------------
! nraci: Accretion of cloud ice by rain 
!        (T<T0: NI->NR)
!-------------------------------------------------------------
! revised
          if(supcol.gt.0. .and. nci(i,k,2).gt.ncmin) then
          if(nrs(i,k,1).gt.nrmin) then
               acrfac=(g3pmr)*rslopemu(i,k,1)*rslope3(i,k,1)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmr)*rslopemu(i,k,1)*rslope(i,k,1)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)
!
                nraci(i,k) =(pi)*n0i(i,k)*n0r(i,k)*eacri*abs(vt2r-vt2i)*acrfac/4.
                nraci(i,k)=nraci(i,k)*min(max(0.0,(qrs(i,k,1))/qci(i,k,2)),1.)**2
                nraci(i,k) = min(nraci(i,k),nci(i,k,2)/dtcld)
!-------------------------------------------------------------
! niacr: Accretion of rain by cloud ice  [LH A25]
!        (T<T0: NR->) 
!-------------------------------------------------------------
               acrfac=(g3pmi)*rslopemu(i,k,4)*rslope3(i,k,4)*g1pmr*rslopemu(i,k,1)*rslope(i,k,1)&
                     +(2.)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)&
                     +(g1pmi)*rslopemu(i,k,4)*rslope(i,k,4)*g3pmr*rslopemu(i,k,1)*rslope3(i,k,1)
!
              niacr(i,k)=(pi)*n0i(i,k)*n0r(i,k)*eacir*abs(vt2i-vt2r)*acrfac/4.
              niacr(i,k) = niacr(i,k)*min(max(0.0,qci(i,k,2)/qrs(i,k,1)),1.)**2
              niacr(i,k) = min(niacr(i,k),nrs(i,k,1)/dtcld)
            endif

!-------------------------------------------------------------
! nsaci: Accretion of cloud ice by snow 
!       (T<T0: NI->NS)
!-------------------------------------------------------------
              if(qrs(i,k,2).gt.qcrmin) then
               acrfac=(g3pms)*rslopemu(i,k,2)*rslope3(i,k,2)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pms*rslopemu(i,k,2)*rslope2(i,k,2)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pms)*rslopemu(i,k,2)*rslope(i,k,2)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)
!
                nsaci(i,k)=(pi)*n0i(i,k)*n0s*n0sfac(i,k)*eacsi*abs(vt2s-vt2i)*acrfac/4.
                nsaci(i,k)=nsaci(i,k)*min(max(0.0,(qrs(i,k,2))/qci(i,k,2)),1.)**2
                nsaci(i,k) = min(nsaci(i,k),nci(i,k,2)/dtcld)
              endif
!-------------------------------------------------------------
! ngaci: Accretion of cloud ice by graupel 
!       (T<T0: NI->NG)
!-------------------------------------------------------------
             if(qrs(i,k,3).gt.qcrmin) then
               eacgi = exp(0.07*(-supcol))
               acrfac=(g3pmg)*rslopemu(i,k,3)*rslope3(i,k,3)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmg*rslopemu(i,k,3)*rslope2(i,k,3)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmg)*rslopemu(i,k,3)*rslope(i,k,3)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)
!
               ngaci(i,k)=(pi)*n0i(i,k)*n0g*eacgi*abs(vt2g(i,k)-vt2i)*acrfac/4.
               ngaci(i,k)=ngaci(i,k)*min(max(0.0,(qrs(i,k,3))/qci(i,k,2)),1.)**2
               ngaci(i,k) = min(ngaci(i,k),nci(i,k,2)/dtcld)
           endif
         endif
!-------------------------------------------------------------
! psacw: Accretion of cloud water by snow  [HL A7] [LFO 24]
!        (T<T0: QC->QS, and T>=T0: QC->QR)
!-------------------------------------------------------------
          if(qrs(i,k,2).gt.qcrmin .and. qci(i,k,1).gt.qmin) then
!            psacw(i,k) = min(pacrc*n0sfac(i,k)*rslope3(i,k,2)*rslopeb(i,k,2)   &
             psacw(i,k) = min((rslope3(i,k,2))*rslopeb(i,k,2)*rslopemu(i,k,2)    &
                         *pi*n0so(i,k)*n0sfac(i,k)*avts*g3pbs*.25*eacsc              &
              ! reduce collection efficiency (suggested by B. Wilt)
                        *min(max(0.0,qrs(i,k,2)/qci(i,k,1)),1.)**2             &
                        *qci(i,k,1)*denfac(i,k),qci(i,k,1)/dtcld)
          endif
!-------------------------------------------------------------
! nsacw: Accretion of cloud water by snow  [LH A12]
!        (NC ->) 
!-------------------------------------------------------------
         if(qrs(i,k,2).gt.qcrmin .and. nci(i,k,1).gt.ncmin) then
!           nsacw(i,k) = min(pacrc*n0sfac(i,k)*rslope3(i,k,2)*rslopeb(i,k,2)    &
           nsacw(i,k) = min((pi)*avts*.25*eacsc*n0so(i,k)*n0sfac(i,k)*n0c(i,k)/(muc+1)  &
                       *g3pbs*rslope3(i,k,2)*rslopeb(i,k,2)*rslopemu(i,k,2)     &
                       *rslopec(i,k)*rslopecmu(i,k)     &
              ! reduce collection efficiency (suggested by B. Wilt)
                       *min(max(0.0,qrs(i,k,2)/qci(i,k,1)),1.)**2              &
                       *denfac(i,k),nci(i,k,1)/dtcld)
         endif
!-------------------------------------------------------------
! pgacw: Accretion of cloud water by graupel [HL A6] [LFO 40]
!        (T<T0: QC->QG, and T>=T0: QC->QR)
!-------------------------------------------------------------
          if(qrs(i,k,3).gt.qcrmin .and. qci(i,k,1).gt.qmin) then
!           pgacw(i,k) = min(pacrg*rslope3(i,k,3)*rslopeb(i,k,3)*qci(i,k,1)    &
             pgacw(i,k) = min((rslope3(i,k,3))*rslopeb(i,k,3)*rslopemu(i,k,3)    &
                         *qci(i,k,1)*pi*n0go(i,k)*avtg(i,k)*g3pbg(i,k)*.25*eacgc&
              ! reduce collection efficiency (suggested by B. Wilt)
                        *min(max(0.0,qrs(i,k,3)/qci(i,k,1)),1.)**2             &
                        *denfac(i,k),qci(i,k,1)/dtcld)
          endif
!-------------------------------------------------------------
! ngacw: Accretion of cloud water by graupel [LH A13]
!        (NC-> 
!-------------------------------------------------------------
          if(qrs(i,k,3).gt.qcrmin .and. nci(i,k,1).gt.ncmin) then
           ngacw(i,k) = min((pi)*avtg(i,k)*.25*eacgc*n0go(i,k)*n0c(i,k)/(muc+1)&
                       *g3pbg(i,k)*rslope3(i,k,3)*rslopeb(i,k,3)*rslopemu(i,k,3)&
                       *rslopec(i,k)*rslopecmu(i,k)     &
              ! reduce collection efficiency (suggested by B. Wilt)
                        *min(max(0.0,qrs(i,k,3)/qci(i,k,1)),1.)**2             &
                        *denfac(i,k),nci(i,k,1)/dtcld)
          endif
!-------------------------------------------------------------
! paacw: Accretion of cloud water by averaged snow/graupel 
!        (T<T0: QC->QG or QS, and T>=T0: QC->QR) 
!-------------------------------------------------------------
          if(qsum(i,k) .gt. 1.e-15 ) then
            paacw(i,k) = (qrs(i,k,2)*psacw(i,k)+qrs(i,k,3)*pgacw(i,k))/(qsum(i,k))
!-------------------------------------------------------------
! naacw: Accretion of cloud water by averaged snow/graupel
!        (Nc->)
!-------------------------------------------------------------
            naacw(i,k) = (qrs(i,k,2)*nsacw(i,k)+qrs(i,k,3)*ngacw(i,k))/(qsum(i,k))
          endif      
!-------------------------------------------------------------
! piacw: Accretion of cloud water by ice 
!        (T<T0: QC->QI)
!-------------------------------------------------------------
         if(supcol.gt.0. .and. qci(i,k,2).gt.qcrmin) then
!PK97(riming not occur on ice smaller than 50-150 micron)
           if(qci(i,k,1).gt.qmin .and. avedia(i,k,3).GE.di50) then
             piacw(i,k) = min(rslope3(i,k,4)*rslopeb(i,k,4)*rslopemu(i,k,4)    &
                         *pi*n0i(i,k)*avti*g3pbi*.25*eacic              &
              ! reduce collection efficiency (suggested by B. Wilt)
                        *min(max(0.0,qci(i,k,2)/qci(i,k,1)),1.)**2             &
                        *qci(i,k,1)*denfac(i,k),qci(i,k,1)/dtcld)
           endif
!-------------------------------------------------------------
! niacw: Accretion of cloud water by ice
!        (T<T0: NC ->NI) 
!-------------------------------------------------------------
          if(nci(i,k,1).gt.ncmin .and. avedia(i,k,3).GE. di50) then
             niacw(i,k) = min(pi*avti*.25*eacic*n0i(i,k)*n0c(i,k)/(muc+1)&
                       *g3pbi*rslope3(i,k,4)*rslopeb(i,k,4)*rslopemu(i,k,4)&
                       *rslopec(i,k)*rslopecmu(i,k)     &
              ! reduce collection efficiency (suggested by B. Wilt)
                       *min(max(0.0,qci(i,k,2)/qci(i,k,1)),1.)**2              &
                       *denfac(i,k),nci(i,k,1)/dtcld)
          endif
        endif
!-------------------------------------------------------------
! pracs: Accretion of snow by rain [HL A11] [LFO 27]
!         (T<T0: QS->QG)
!-------------------------------------------------------------
          if(qrs(i,k,2).gt.qcrmin .and. qrs(i,k,1).gt.qcrmin) then
            if(supcol.gt.0) then
!              acrfac = 5.*rslope3(i,k,2)*rslope3(i,k,2)                        &
!                      + 4.*rslope3(i,k,2)*rslope2(i,k,2)*rslope(i,k,1)         &
!                      + 1.5*rslope2(i,k,2)*rslope2(i,k,2)*rslope2(i,k,1)
            acrfac = (g3pmr)*g1pdsms*rslope3(i,k,1)*rslopemu(i,k,1)        &
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope(i,k,2)             &
                     +(2.)*g2pmr*g2pdsms*rslope2(i,k,1)*rslopemu(i,k,1)&
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope2(i,k,2)            &
                     +(g1pmr)*g3pdsms*rslope(i,k,1)*rslopemu(i,k,1)&
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope3(i,k,2)
!              pracs(i,k) = pi*pi*ncr(i,k,3)*n0s*n0sfac(i,k)*abs(vt2r-vt2ave)   &
!                          *(dens/den(i,k))*acrfac
              pracs(i,k) =(pi)*cms*n0so(i,k)*n0sfac(i,k)*n0r(i,k)*abs(vt2r-vt2s)&
                        /(4*den(i,k))*acrfac*eacrs
              ! reduce collection efficiency (suggested by B. Wilt)
              pracs(i,k) =pracs(i,k)*min(max(0.0,(qrs(i,k,1))/qrs(i,k,2)),1.)**2
              pracs(i,k) = min(pracs(i,k),(qrs(i,k,2))/dtcld)
            endif
!-------------------------------------------------------------
! nracs: Accretion of snow by rain [HL A11] [LFO 27]
!         (T<T0: NS->NG)
!-------------------------------------------------------------
!          if(qrs(i,k,2).gt.qcrmin .and. qrs(i,k,1).gt.qcrmin) then
!            if(supcol.gt.0) then
!              acrfac=g3pmr*rslopemu(i,k,1)*rslope3(i,k,1)*g1pms*rslopemu(i,k,2)*rslope(i,k,2)&
!                     +2.*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)*g2pms*rslopemu(i,k,2)*rslope2(i,k,2)&
!                     +g1pmr*rslopemu(i,k,1)*rslope(i,k,1)*g3pms*rslopemu(i,k,2)*rslope3(i,k,2)
!
!              nracs(i,k)=pi/(4.)*n0s*n0sfac(i,k)*n0r(i,k)*eacrs*abs(vt2r-vt2ave)*acrfac
!                  ! reduce collection efficiency (suggested by B. Wilt)
!              nracs(i,k) = nracs(i,k)*min(max(0.0,qrs(i,k,1)/qrs(i,k,2)),1.)**2
!              nracs(i,k) = min(nracs(i,k),qrs(i,k,2)/dtcld)
!              endif
!            endif
!-------------------------------------------------------------
! psacr: Accretion of rain by snow [HL A10] [LFO 28]
!         (T<T0:QR->QS or QR->QG) (T>=T0: enhance melting of snow)
!-------------------------------------------------------------
!            acrfac = 30.*rslope3(i,k,1)*rslope2(i,k,1)*rslope(i,k,2)           &
!                     +10.*rslope2(i,k,1)*rslope2(i,k,1)*rslope2(i,k,2)         & 
!                     + 2.*rslope3(i,k,1)*rslope3(i,k,2)
! revised 
            acrfac = (g3pms)*g1pdrmr*rslope3(i,k,2)*rslopemu(i,k,2) &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)             &
                     +(2.)*g2pms*g2pdrmr*rslope2(i,k,2)*rslopemu(i,k,2)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)            &
                     +(g1pms)*g3pdrmr*rslope(i,k,2)*rslopemu(i,k,2)      &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)
            psacr(i,k) = (pi)*cmr*n0r(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2r)&
                        /(4*den(i,k))*acrfac*eacsr
              ! reduce collection efficiency (suggested by B. Wilt)
            psacr(i,k) = psacr(i,k)*min(max(0.0,(qrs(i,k,2))/qrs(i,k,1)),1.)**2
            psacr(i,k) = min(psacr(i,k),(qrs(i,k,1))/dtcld)
          endif
          if(qrs(i,k,2).gt.qcrmin .and. nrs(i,k,1).gt.nrmin) then
!-------------------------------------------------------------
! nsacr: Accretion of rain by snow  [LH A23] 
!       (T<T0:NR->)
!-------------------------------------------------------------
!            acrfac = 1.5*rslope2(i,k,1)*rslope(i,k,2)                          &
!                    + 1.0*rslope(i,k,1)*rslope2(i,k,2)+.5*rslope3(i,k,2)        
! revised
            acrfac = (g3pms)*g1pmr*rslope3(i,k,2)*rslopemu(i,k,2)&
                     *rslope(i,k,1)*rslopemu(i,k,1)                            &
                    +(2.)*g2pms*g2pmr*rslope2(i,k,2)*rslopemu(i,k,2)&
                     *rslope2(i,k,1)*rslopemu(i,k,1)                           &
                    +(g1pms)*g3pmr*rslope(i,k,2)*rslopemu(i,k,2)&
                     *rslope3(i,k,1)*rslopemu(i,k,1)
            nsacr(i,k) =(pi)/4.*n0r(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2r)        &
                        *acrfac*eacsr
              ! reduce collection efficiency (suggested by B. Wilt)
            nsacr(i,k) = nsacr(i,k)*min(max(0.0,qrs(i,k,2)/qrs(i,k,1)),1.)**2
            nsacr(i,k) = min(nsacr(i,k),nrs(i,k,1)/dtcld)
          endif
!-------------------------------------------------------------
! pgacr: Accretion of rain by graupel [HL A12] [LFO 42]
!         (T<T0: QR->QG) (T>=T0: enhance melting of graupel)
!-------------------------------------------------------------
          if(qrs(i,k,3).gt.qcrmin .and. qrs(i,k,1).gt.qcrmin) then
!            acrfac = 30.*rslope3(i,k,1)*rslope2(i,k,1)*rslope(i,k,3)           &
!                    +10.*rslope2(i,k,1)*rslope2(i,k,1)*rslope2(i,k,3)          & 
!                    + 2.*rslope3(i,k,1)*rslope3(i,k,3)
            acrfac = (g3pmg)*g1pdrmr*rslope3(i,k,3)*rslopemu(i,k,3)     &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)             &
                     +(2.)*g2pmg*g2pdrmr*rslope2(i,k,3)*rslopemu(i,k,3)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)            &
                     +(g1pmg)*g3pdrmr*rslope(i,k,3)*rslopemu(i,k,3)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)
            pgacr(i,k) = (pi)*cmr*n0r(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2r)     &
                        /(4*den(i,k))*acrfac*eacgr
!            pgacr(i,k) = pi*pi*ncr(i,k,3)*n0g*abs(vt2ave-vt2r)*(denr/den(i,k))  &
!                        *acrfac
              ! reduce collection efficiency (suggested by B. Wilt)
            pgacr(i,k) =pgacr(i,k)*min(max(0.0,(qrs(i,k,3))/qrs(i,k,1)),1.)**2
            pgacr(i,k) = min(pgacr(i,k),(qrs(i,k,1))/dtcld)
          endif
!-------------------------------------------------------------
! ngacr: Accretion of rain by graupel  [LH A24] 
!        (T<T0: NR->) 
!-------------------------------------------------------------
          if(qrs(i,k,3).gt.qcrmin .and. nrs(i,k,1).gt.nrmin) then
! revised
            acrfac = (g3pmg)*g1pmr*rslope3(i,k,3)*rslopemu(i,k,3)&
                     *rslope(i,k,1)*rslopemu(i,k,1)                            &
                    +(2.)*g2pmg*g2pmr*rslope2(i,k,3)*rslopemu(i,k,3)&
                     *rslope2(i,k,1)*rslopemu(i,k,1)                           &
                    +(g1pmg)*g3pmr*rslope(i,k,3)*rslopemu(i,k,3)&
                     *rslope3(i,k,1)*rslopemu(i,k,1)
            ngacr(i,k)=(pi)/4.*n0r(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2r)*acrfac*eacgr
              ! reduce collection efficiency (suggested by B. Wilt)
            ngacr(i,k) = ngacr(i,k)*min(max(0.0,qrs(i,k,3)/qrs(i,k,1)),1.)**2
            ngacr(i,k) = min(ngacr(i,k),nrs(i,k,1)/dtcld)
          endif

!-------------------------------------------------------------------------------
! pmulcs, pmulrs, pmulcg, pmulrg   : Hallet & Mossop 1974
! nmulcs, nmulrs, nmulcg, nmulrg   : ice multiplication 
! QC-> QI, QR -> QI
!--------------------------------------------------------------------------------
         Mispl = 4./3.*pi*deni*(Rispl)**3 !DENI=500;

         IF (qrs(i,k,2).GE.0.1E-3) THEN
         IF (qci(i,k,1).GE.0.5E-3.OR.qrs(i,k,1).GE.0.1E-3) THEN
         IF (paacw(i,k).GT.0..OR.psacr(i,k).GT.0.) THEN
            IF (t(i,k).LT.270.16 .AND. t(i,k).GT.265.16) THEN

               IF (t(i,k).GT.270.16) THEN
                  fmul = 0.
               ELSE IF (t(i,k).LE.270.16.AND.t(i,k).GT.268.16)  THEN
                  fmul = (270.16-t(i,k))/2.
               ELSE IF (t(i,k).GE.265.16.AND.t(i,k).LE.268.16)   THEN
                  fmul = (t(i,k)-265.16)/3.
               ELSE IF (t(i,k).LT.265.16) THEN
                  fmul= 0.
               END IF

! 1000 IS TO CONVERT FROM KG TO G

! SPLINTERING FROM DROPLETS ACCRETED ONTO SNOW

               IF (paacw(i,k).GT.0.) THEN
                  nmulcs(i,k) = 35.E4*paacw(i,k)*fmul*1000. ![kg/g]
                  pmulcs(i,k) = nmulcs(i,k)*Mispl

! CONSTRAIN SO THAT TRANSFER OF MASS FROM SNOW TO ICE CANNOT BE MORE MASS
! THAN WAS RIMED ONTO SNOW
                  pmulcs(i,k) = MIN(pmulcs(i,k),paacw(i,k))
                  paacw(i,k) = paacw(i,k)-pmulcs(i,k)
                  nmulcs(i,k) = nmulcs(i,k)*den(i,k)

               END IF

! RIMING AND SPLINTERING FROM ACCRETED RAINDROPS

               IF (psacr(i,k).GT.0.) THEN
                   nmulrs(i,k) = 35.E4*psacr(i,k)*fmul*1000.
                   pmulrs(i,k) = nmulrs(i,k)*Mispl

! CONSTRAIN SO THAT TRANSFER OF MASS FROM SNOW TO ICE CANNOT BE MORE MASS
! THAN WAS RIMED ONTO SNOW

                   pmulrs(i,k) = MIN(pmulrs(i,k),psacr(i,k))
                   psacr(i,k) = psacr(i,k)-pmulrs(i,k)
                   nmulrs(i,k) = nmulrs(i,k)*den(i,k)

               END IF

            END IF
         END IF
         END IF
         END IF
!-----------------------------------------------------------------------------
         IF (qrs(i,k,3).GE.0.1E-3) THEN
         IF (qci(i,k,1).GE.0.5E-3.OR.qrs(i,k,1).GE.0.1E-3) THEN
         IF (paacw(i,k).GT.0..OR.pgacr(i,k).GT.0.) THEN
            IF (t(i,k).LT.270.16 .AND. t(i,k).GT.265.16) THEN

               IF (t(i,k).GT.270.16) THEN
                  fmul = 0.
               ELSE IF (t(i,k).LE.270.16.AND.t(i,k).GT.268.16)  THEN
                  fmul = (270.16-t(i,k))/2.
               ELSE IF (t(i,k).GE.265.16.AND.t(i,k).LE.268.16)   THEN
                  fmul = (t(i,k)-265.16)/3.
               ELSE IF (t(i,k).LT.265.16) THEN
                  fmul = 0.
               END IF

! 1000 IS TO CONVERT FROM KG TO G

! SPLINTERING FROM DROPLETS ACCRETED ONTO GRAUPEL

               IF (paacw(i,k).GT.0.) THEN
                  nmulcg(i,k) = 35.E4*paacw(i,k)*fmul*1000.
                  pmulcg(i,k) = nmulcg(i,k)*Mispl

! CONSTRAIN SO THAT TRANSFER OF MASS FROM GRAUPEL TO ICE CANNOT BE MORE MASS
! THAN WAS RIMED ONTO GRAUPEL

                  pmulcg(i,k) = MIN(pmulcg(i,k),paacw(i,k))
                  paacw(i,k) = paacw(i,k)-pmulcg(i,k)
                  nmulcg(i,k) = nmulcg(i,k)*den(i,k)

               END IF


! RIMING AND SPLINTERING FROM ACCRETED RAINDROPS

               IF (pgacr(i,k).GT.0.) THEN
                   nmulrg(i,k) = 35.E4*pgacr(i,k)*fmul*1000.
                   pmulrg(i,k) = nmulrg(i,k)*Mispl

! CONSTRAIN SO THAT TRANSFER OF MASS FROM GRAUPEL TO ICE CANNOT BE MORE MASS
! THAN WAS RIMED ONTO GRAUPEL

                   pmulrg(i,k) = MIN(pmulrg(i,k),pgacr(i,k))
                   pgacr(i,k) = pgacr(i,k)-pmulrg(i,k)
                   nmulrg(i,k) = nmulrg(i,k)*den(i,k)

               END IF              
              END IF
           END IF
           END IF
           END IF
!-------------------------------------------------------------
! pgacs: Accretion of snow by graupel [HL A13] [LFO 29]
!        (QS->QG) : This process is eliminated in V3.0 with the
!        new combined snow/graupel fall speeds
!-------------------------------------------------------------
          if(qrs(i,k,3).gt.qcrmin .and. qrs(i,k,2).gt.qcrmin) then
            pgacs(i,k) = 0. 
          endif
          if(supcol.le.0) then
            xlf = xlf0
!-------------------------------------------------------------
! pseml: Enhanced melting of snow by accretion of water [HL A34]
!        (T>=T0: QS->QR)
!-------------------------------------------------------------
            if(qrs(i,k,2).gt.0.)                                               & 
              pseml(i,k) = min(max((cliq)*supcol*(paacw(i,k)+psacr(i,k)) &
                          /xlf,-(qrs(i,k,2))/dtcld),0.)
!--------------------------------------------------------------
! nseml: Enhanced melting of snow by accretion of water    [LH A29]
!        (T>=T0: ->NR)
!--------------------------------------------------------------
              if  (qrs(i,k,2).gt.qcrmin) then
                sfac = (rslope(i,k,2))*n0so(i,k)*n0sfac(i,k)/qrs(i,k,2)
                nseml(i,k) = -sfac*pseml(i,k)
              endif
!-------------------------------------------------------------
! pgeml: Enhanced melting of graupel by accretion of water [HL A24] [RH84 A21-A22]
!        (T>=T0: QG->QR)
!-------------------------------------------------------------
            if(qrs(i,k,3).gt.0.)                                               &
              pgeml(i,k) = min(max((cliq)*supcol*(paacw(i,k)+pgacr(i,k))/xlf &
                          ,-(qrs(i,k,3))/dtcld),0.)
!--------------------------------------------------------------
! ngeml: Enhanced melting of graupel by accretion of water [LH A30] 
!         (T>=T0: -> NR)
!--------------------------------------------------------------
              if (qrs(i,k,3).gt.qcrmin) then
                gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
                ngeml(i,k) = -gfac*pgeml(i,k)
              endif
          endif

!-------------------------------------------------------------
! pinud: generation(nucleation) of ice from vapor 
!       (T<T0: QV->QI)  (old: pigen)
! ninud (        ->NI)
!-------------------------------------------------------------
          if( (supcol.gt.8 .and. supsat .gt. 0.) .or. &
              (rh(i,k,2) .gt. 1.08) )then
              supice = satdt-prevp(i,k)
              Minud = 4./3.*pi*deni*(Rinud)**3 ! 2.e-12 kg
!
              Nid =0.005*exp(0.304*(supcol))*1000. !cooper curve

! limit to 500 m-3 
! ice nuclei concentrations are large when very cold temp

              Nid = max(min(Nid,500.e3),0.) !m-3
              if (Nid.GT.nci(i,k,2)) then
                ninud(i,k) = ((Nid)-(nci(i,k,2)))/dtcld
                pinud(i,k) = ninud(i,k)/den(i,k)*Minud
                pinud(i,k) = min(min(pinud(i,k),(satdt)/2),supice)
                ninud(i,k) = pinud(i,k)*den(i,k)/Minud
              endif
             if(abs(prevp(i,k)+pinud(i,k)).ge.abs(satdt)) ifsat = 1     
           endif

          if(supcol.gt.0) then
!-------------------------------------------------------------
! pidep: Deposition/Sublimation rate of ice [HDC 9]
!       (T<T0: QV->QI or QI->QV)
!-------------------------------------------------------------
            if(qci(i,k,2).gt.0. .and. ifsat.ne.1) then
              pidep(i,k)=(4.)*n0i(i,k)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*(rh(i,k,2)-1.) &
                        /work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)

              if(pidep(i,k).lt.0.) then
!--------------------------------------------------------------
! nisub (Park and Lim,2023 & Kwon et al.,2023)
!--------------------------------------------------------------
              if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then
                 nci(i,k,2) = 0.
              endif
                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)
                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)
              else
                pidep(i,k) = min(min(pidep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)).ge.abs(satdt)) ifsat = 1
            endif
!-------------------------------------------------------------
! psdep: deposition/sublimation rate of snow [HDC 14]
!        (T<T0: QV->QS or QS->QV)
!-------------------------------------------------------------
            if(qrs(i,k,2).gt.0. .and. ifsat.ne.1) then
!revised
              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2)) &
                      *rslopemu(i,k,2)
              psdep(i,k) =(rh(i,k,2)-1.)*n0sfac(i,k)*((precs1)*n0so(i,k)*rslope2(i,k,2)   &
                        *rslopemu(i,k,2) +(precs2)*n0so(i,k)*work2(i,k)*coeres)/work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)-pidep(i,k)
              if(psdep(i,k).lt.0.) then
                psdep(i,k) = max(psdep(i,k),-(qrs(i,k,2))/dtcld)
                psdep(i,k) = max(max(psdep(i,k),(satdt)/2),supice)
              else
                psdep(i,k) = min(min(psdep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)+psdep(i,k)).ge.abs(satdt)) ifsat = 1
            endif
!-------------------------------------------------------------
! pgdep: deposition/sublimation rate of graupel [HL A21] [LFO 46]
!        (T<T0: QV->QG or QG->QV)
!-------------------------------------------------------------
            if(qrs(i,k,3).gt.0. .and. ifsat.ne.1) then
!revised
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3)) &
                      *rslopemu(i,k,3)
              pgdep(i,k) =(rh(i,k,2)-1.)*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3)&
                          +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)-pidep(i,k)-psdep(i,k)
              if(pgdep(i,k).lt.0.) then
                pgdep(i,k) = max(pgdep(i,k),-(qrs(i,k,3))/dtcld)
                pgdep(i,k) = max(max(pgdep(i,k),(satdt)/2),supice)
              else
                pgdep(i,k) = min(min(pgdep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)+psdep(i,k)+pgdep(i,k)).ge.          &
                abs(satdt)) ifsat = 1
            endif
!-------------------------------------------------------------
! psaut: conversion(aggregation) of ice to snow [HDC 12]
!        (T<T0: QI->QS)
!-------------------------------------------------------------
            if(qci(i,k,2).gt.0. .and. nci(i,k,2).gt.0) then
!Ryan et al 2010.
              IF (t(i,k).GT.255.66) THEN
                qi0 = 0.4632*10**(-6.0-0.0413*(-supcol))*den(i,k)
              ELSE 
                qi0 = 0.2316*10**(-4.0+0.0519*(-supcol))*den(i,k)
              END IF
              alpha1= 0.005*exp(0.025*(-supcol)) ![s-1]
              Miaut= pi*deni*(di125)**3/6.  ![kg]
              psaut(i,k) = min(max(0.,alpha1*(qci(i,k,2)-qi0)),qci(i,k,2)/dtcld)
              nsaut(i,k) = min((psaut(i,k))*den(i,k)/Miaut,nci(i,k,2)/dtcld)  
            endif
!
!-------------------------------------------------------------
! pgaut: conversion(aggregation) of snow to graupel [HL A4] [LFO 37]
!        (T<T0: QS->QG)
!-------------------------------------------------------------
!            if(qrs(i,k,2).gt.0.) then
!              alpha2 = 1.e-3*exp(0.09*(-supcol))
!              pgaut(i,k) = min(max(0.,alpha2*(qrs(i,k,2)-qs0)),qrs(i,k,2)/dtcld)
!            endif
          endif
!
!-------------------------------------------------------------
! psevp: Evaporation of melting snow [HL A35] [RH83 A27]
!       (T>=T0: QS->QV)
!-------------------------------------------------------------
          if(supcol.lt.0.) then
            if(qrs(i,k,2).gt.0. .and. rh(i,k,1).lt.1.) then
              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2))  &
                      *rslopemu(i,k,2)
              psevp(i,k) =(rh(i,k,1)-1.)*n0sfac(i,k)*((precs1)*n0so(i,k)*rslope2(i,k,2)   &
                        *rslopemu(i,k,2)+(precs2)*n0so(i,k)*work2(i,k)*coeres)/work1(i,k,1)
              psevp(i,k) = min(max(psevp(i,k),-(qrs(i,k,2))/dtcld),0.)
            endif
!-------------------------------------------------------------
! pgevp: Evaporation of melting graupel [HL A25] [RH84 A19]
!       (T>=T0: QG->QV)
!-------------------------------------------------------------
            if(qrs(i,k,3).gt.0. .and. rh(i,k,1).lt.1.) then
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))  &
                      *rslopemu(i,k,3)
              pgevp(i,k) =(rh(i,k,1)-1.)*((precg1)*n0go(i,k)*rslope2(i,k,3)        &
                      *rslopemu(i,k,3)+(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/work1(i,k,1)
              pgevp(i,k) = min(max(pgevp(i,k),-(qrs(i,k,3))/dtcld),0.)
            endif
          endif
        enddo
      enddo
!----------------------------------------------------------------
!     check mass conservation of generation terms and feedback to the
!     large scale
!
      do k = kts, kte
        do i = its, ite
!
          delta2=0.
          delta3=0.
          if(qrs(i,k,1).lt.1.e-4 .and. qrs(i,k,2).lt.1.e-4) delta2=1.
          if(qrs(i,k,1).lt.1.e-4) delta3=1.
          if(t(i,k).le.t0c) then
!
!     cloud water
!
            value = max(qmin,qci(i,k,1))
            source = (praut(i,k)+pracw(i,k)+paacw(i,k)+paacw(i,k)+piacw(i,k)        &
                    +pmulcs(i,k)+pmulcg(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              piacw(i,k) = piacw(i,k)*factor
              pmulcs(i,k) = pmulcs(i,k)*factor
              pmulcg(i,k) = pmulcg(i,k)*factor
            endif
!
!     cloud ice
!
            value = max(qmin,qci(i,k,2))
            source = (psaut(i,k)-pinud(i,k)-pidep(i,k)+praci(i,k)+psaci(i,k)   &
             +pgaci(i,k)-pmulcs(i,k)-pmulrs(i,k)-pmulcg(i,k)-pmulrg(i,k)-piacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              psaut(i,k) = psaut(i,k)*factor
              pinud(i,k) = pinud(i,k)*factor
              pidep(i,k) = pidep(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psaci(i,k) = psaci(i,k)*factor
              pgaci(i,k) = pgaci(i,k)*factor
              piacw(i,k) = piacw(i,k)*factor
              pmulcs(i,k) = pmulcs(i,k)*factor
              pmulrs(i,k) = pmulrs(i,k)*factor
              pmulcg(i,k) = pmulcg(i,k)*factor
              pmulrg(i,k) = pmulrg(i,k)*factor
            endif
!
!     rain
!
            value = max(qmin,qrs(i,k,1))
            source = (-praut(i,k)-prevp(i,k)-pracw(i,k)+piacr(i,k)             &
                    +psacr(i,k)+pgacr(i,k)+pmulrs(i,k)+pmulrg(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              prevp(i,k) = prevp(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pgacr(i,k) = pgacr(i,k)*factor
              pmulrs(i,k) = pmulrs(i,k)*factor
              pmulrg(i,k) = pmulrg(i,k)*factor
            endif
!
!     snow
!
            value = max(qmin,qrs(i,k,2))
            source = -(psdep(i,k)+psaut(i,k)-pgaut(i,k)+paacw(i,k)             &
                     +piacr(i,k)*delta3+praci(i,k)*delta3                      &
                     -pracs(i,k)*(1.-delta2)+psacr(i,k)*delta2                 &
                     +psaci(i,k)-pgacs(i,k) )*dtcld
            if (source.gt.value) then
              factor = value/source
              psdep(i,k) = psdep(i,k)*factor
              psaut(i,k) = psaut(i,k)*factor
              pgaut(i,k) = pgaut(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psaci(i,k) = psaci(i,k)*factor
              pracs(i,k) = pracs(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pgacs(i,k) = pgacs(i,k)*factor
            endif
!
!     graupel
!
            value = max(qmin,qrs(i,k,3))
            source = -(pgdep(i,k)+pgaut(i,k)                                   &
                     +piacr(i,k)*(1.-delta3)+praci(i,k)*(1.-delta3)            &
                     +psacr(i,k)*(1.-delta2)+pracs(i,k)*(1.-delta2)            &
                     +pgaci(i,k)+paacw(i,k)+pgacr(i,k)+pgacs(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgdep(i,k) = pgdep(i,k)*factor
              pgaut(i,k) = pgaut(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pracs(i,k) = pracs(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              pgaci(i,k) = pgaci(i,k)*factor
              pgacr(i,k) = pgacr(i,k)*factor
              pgacs(i,k) = pgacs(i,k)*factor
            endif
!
!     cloud
!
            value = max(ncmin,nci(i,k,1))
            source = (nraut(i,k)+nccol(i,k)+nracw(i,k)                         &
                    +niacw(i,k)+naacw(i,k)+naacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nccol(i,k) = nccol(i,k)*factor
              nracw(i,k) = nracw(i,k)*factor
              naacw(i,k) = naacw(i,k)*factor
              niacw(i,k) = niacw(i,k)*factor
            endif
!
!     cloud ice
!
            value = max(ncmin,nci(i,k,2))
            source = (nraci(i,k)+nsaci(i,k)+ngaci(i,k)+niacr(i,k)+nsaut(i,k)        &
              -nmulcs(i,k)-nmulcg(i,k)-nmulrs(i,k)-nmulrg(i,k)-ninud(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraci(i,k) = nraci(i,k)*factor
              nsaci(i,k) = nsaci(i,k)*factor
              ngaci(i,k) = ngaci(i,k)*factor
              niacr(i,k) = niacr(i,k)*factor
              nsaut(i,k) = nsaut(i,k)*factor
              ninud(i,k) = ninud(i,k)*factor
              nmulcs(i,k) = nmulcs(i,k)*factor
              nmulcg(i,k) = nmulcg(i,k)*factor
              nmulrs(i,k) = nmulrs(i,k)*factor
              nmulrg(i,k) = nmulrg(i,k)*factor
            endif
!
!     rain
!
            value = max(nrmin,nrs(i,k,1))
            source = (-nraut(i,k)+nraci(i,k)+nrcol(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraci(i,k) = nraci(i,k)*factor
              nraut(i,k) = nraut(i,k)*factor
              nrcol(i,k) = nrcol(i,k)*factor
              niacr(i,k) = niacr(i,k)*factor
              nsacr(i,k) = nsacr(i,k)*factor
              ngacr(i,k) = ngacr(i,k)*factor
            endif

            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))
!
!     graupel volume mixing ratio
!
              biacr(i,k) = piacr(i,k)/denr
              baacw(i,k) = paacw(i,k)/denr
              bsacr(i,k) = psacr(i,k)/denr
              braci(i,k) = praci(i,k)/deni
              bracs(i,k) = pracs(i,k)/dens
              bsaci(i,k) = psaci(i,k)/deni
              bsaut(i,k) = psaut(i,k)/deni
              bgaci(i,k) = pgaci(i,k)/deni
              bgacr(i,k) = pgacr(i,k)/denr
              bsdep(i,k)=psdep(i,k)/dens

!     update
            q(i,k) = q(i,k)+work2(i,k)*dtcld 
            qci(i,k,1) = max(qci(i,k,1)-(praut(i,k)+pracw(i,k)                 &
                          +piacw(i,k) +paacw(i,k)+paacw(i,k)+pmulcs(i,k)       &
                          +pmulcg(i,k))*dtcld,0.)
            nci(i,k,1) = max(nci(i,k,1)+(-nraut(i,k)-nccol(i,k)-nracw(i,k)     &
                          -niacw(i,k)-naacw(i,k)-naacw(i,k))*dtcld,0.)
            qrs(i,k,1) = max(qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                           +prevp(i,k)-piacr(i,k)-pgacr(i,k)                   &
                           -psacr(i,k)-pmulrs(i,k)-pmulrg(i,k))*dtcld,0.)
            nrs(i,k,1) = max(nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k)      &
                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld,0.)
            qci(i,k,2) = max(qci(i,k,2)-(psaut(i,k)+praci(i,k)                 &
                           +psaci(i,k)+pgaci(i,k)-pinud(i,k)-pidep(i,k)        &
                           -piacw(i,k)-pmulcs(i,k)-pmulcg(i,k)-pmulrs(i,k)     &
                           -pmulrg(i,k))*dtcld,0.)
            nci(i,k,2) = max(nci(i,k,2)+(-nraci(i,k)-nsaci(i,k)-ngaci(i,k)     &
                           -niacr(i,k)+ninud(i,k)+nmulcs(i,k)+nmulcg(i,k)      &
                           +nmulrs(i,k)+nmulrg(i,k)-nsaut(i,k))*dtcld,0.)
            qrs(i,k,2) = max(qrs(i,k,2)+(psdep(i,k)+psaut(i,k)+paacw(i,k)      &
                           -pgaut(i,k)+piacr(i,k)*delta3                       &
                           +praci(i,k)*delta3+psaci(i,k)-pgacs(i,k)            &
                           -pracs(i,k)*(1.-delta2)+psacr(i,k)*delta2)          &
                           *dtcld,0.)
            qrs(i,k,3) = max(qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)                 &
                           +piacr(i,k)*(1.-delta3)                             &
                           +praci(i,k)*(1.-delta3)+psacr(i,k)*(1.-delta2)      &
                           +pracs(i,k)*(1.-delta2)+pgaci(i,k)+paacw(i,k)       &
                           +pgacr(i,k)+pgacs(i,k))*dtcld,0.)
            brs(i,k) = max(brs(i,k)+(pgdep(i,k)/rhox(i,k)+biacr(i,k)           &
                           +braci(i,k)+bsacr(i,k)+bracs(i,k)+bgaci(i,k)        &
                           +baacw(i,k)+bgacr(i,k))*dtcld,0.)
            xlf = xls-xl(i,k)
            xlwork2 = -xls*(psdep(i,k)+pgdep(i,k)+pidep(i,k)+pinud(i,k))       &
                      -xl(i,k)*prevp(i,k)-xlf*(piacr(i,k)+paacw(i,k)           &
                      +pmulcs(i,k)+pmulcg(i,k)+pmulrs(i,k)+pmulrg(i,k)         &
                      +piacw(i,k) +paacw(i,k)+pgacr(i,k)+psacr(i,k)) 
            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld

          else
!
!     cloud water
!
            value = max(qmin,qci(i,k,1))
            source= (praut(i,k)+pracw(i,k)+paacw(i,k)+paacw(i,k))              &
                   *dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
            endif
!
!     rain
!
            value = max(qmin,qrs(i,k,1))
            source = (-paacw(i,k)-praut(i,k)+pseml(i,k)+pgeml(i,k)             &
                     -pracw(i,k)-paacw(i,k)-prevp(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              prevp(i,k) = prevp(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              pseml(i,k) = pseml(i,k)*factor
              pgeml(i,k) = pgeml(i,k)*factor
            endif
!
!     snow
!
            value = max(qcrmin,qrs(i,k,2))
            source=(pgacs(i,k)-pseml(i,k)-psevp(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgacs(i,k) = pgacs(i,k)*factor
              psevp(i,k) = psevp(i,k)*factor
              pseml(i,k) = pseml(i,k)*factor
            endif
!
!     graupel
!
            value = max(qcrmin,qrs(i,k,3))
            source=-(pgacs(i,k)+pgevp(i,k)+pgeml(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgacs(i,k) = pgacs(i,k)*factor
              pgevp(i,k) = pgevp(i,k)*factor
              pgeml(i,k) = pgeml(i,k)*factor
            endif
!
!     cloud
!
            value = max(ncmin,nci(i,k,1))
            source = (+nraut(i,k)+nccol(i,k)+nracw(i,k)+naacw(i,k)             &
                     +naacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nccol(i,k) = nccol(i,k)*factor
              nracw(i,k) = nracw(i,k)*factor
              naacw(i,k) = naacw(i,k)*factor
            endif
!
!     rain
!
            value = max(nrmin,nrs(i,k,1))
            source = (-nraut(i,k)+nrcol(i,k)-nseml(i,k)-ngeml(i,k)             &
                      )*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nrcol(i,k) = nrcol(i,k)*factor
              nseml(i,k) = nseml(i,k)*factor
              ngeml(i,k) = ngeml(i,k)*factor
            endif
!
            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))
!
!     graupel volume mixing ratio
!
            bgevp(i,k)=pgevp(i,k)/rhox(i,k)
            bgeml(i,k)=pgeml(i,k)/rhox(i,k)
!     update
            q(i,k) = q(i,k)+work2(i,k)*dtcld
            qci(i,k,1) = max(qci(i,k,1)-(praut(i,k)+pracw(i,k)                 &
                    +paacw(i,k)+paacw(i,k))*dtcld,0.)
            qrs(i,k,1) = max(qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                    +prevp(i,k)+paacw(i,k)+paacw(i,k)-pseml(i,k)               &
                    -pgeml(i,k))*dtcld,0.)
            qrs(i,k,2) = max(qrs(i,k,2)+(psevp(i,k)-pgacs(i,k)                 &
                    +pseml(i,k))*dtcld,0.)
            qrs(i,k,3) = max(qrs(i,k,3)+(pgacs(i,k)+pgevp(i,k)                 &
                    +pgeml(i,k))*dtcld,0.)
            nci(i,k,1) = max(nci(i,k,1)+(-nraut(i,k)-nccol(i,k)-nracw(i,k)     &
                   -naacw(i,k)-naacw(i,k))*dtcld,0.)
            nrs(i,k,1) = max(nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)+nseml(i,k)      &
                           +ngeml(i,k))*dtcld,0.)
            brs(i,k) = max(brs(i,k)+(bgevp(i,k)+bgeml(i,k))*dtcld,0.)
            xlf = xls-xl(i,k)
            xlwork2 = -xl(i,k)*(prevp(i,k)+psevp(i,k)+pgevp(i,k))              &
                      -xlf*(pseml(i,k)+pgeml(i,k))
            t(i,k) = t(i,k)-xlwork2/cpm(i,k)*dtcld
          endif
        enddo
      enddo
!
     do k = kts,kte
       do i = its,ite
         qrs_tmp(i,k,1) = qrs(i,k,1)
         qrs_tmp(i,k,2) = qrs(i,k,2)
         qrs_tmp(i,k,3) = qrs(i,k,3)
         qci_tmp(i,k) = qci(i,k,2)
         nci_tmp(i,k) = nci(i,k,2)
         nrs_tmp(i,k) = nrs(i,k,1)
         rhox(i,k) = max(rhox(i,k) ,0.)
       enddo
     enddo
!
   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)

      do k = kts, kte
        do i = its, ite
!--------------------------------------------------------------------
! compute the mean-volume drop diameter                   [LH A7]
! for cloud-droplet distribution
!--------------------------------------------------------------------
          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopecmu(i,k) = rslopecmmax
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),den(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif

          avedia(i,k,1) = rslopec(i,k)*(g3pmc)**(1./3.)
          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))
          avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))
!
! Picons, Nicons (Park and Lim, 2023)
!
!
        if (qci(i,k,2).ge. qmin .and.t(i,k).lt.273.15) then
        if (avedia(i,k,3).ge. 200.e-6) then
           qrs(i,k,2) = qrs(i,k,2) + qci(i,k,2)
           qci(i,k,2) = 0.
           nci(i,k,2) = 0.
        end if
        end if
       enddo
      enddo

!
! Inline expansion for fpvs
!         qs(i,k,1) = fpvs(t(i,k),0,rd,rv,cpv,cliq,cice,xlv0,xls,psat,t0c)
!         qs(i,k,2) = fpvs(t(i,k),1,rd,rv,cpv,cliq,cice,xlv0,xls,psat,t0c)
      hsub = xls
      hvap = xlv0
      cvap = cpv
      ttp=t0c+0.01
      dldt=cvap-cliq
      xa=-dldt/rv
      xb=xa+hvap/(rv*ttp)
      dldti=cvap-cice
      xai=-dldti/rv
      xbi=xai+hsub/(rv*ttp)
      do k = kts, kte
        do i = its, ite
          tr=ttp/t(i,k)
          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))
          qs(i,k,1) = max(qs(i,k,1),qmin)
          tr=ttp/t(i,k)
          if(t(i,k).lt.ttp) then
            qs(i,k,2)=psat*exp(log(tr)*(xai))*exp(xbi*(1.-tr))
          else
            qs(i,k,2)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          endif
          qs(i,k,2) = min(qs(i,k,2),0.99*p(i,k))
          qs(i,k,2) = ep2 * qs(i,k,2) / (p(i,k) - qs(i,k,2))
          qs(i,k,2) = max(qs(i,k,2),qmin)
          rh(i,k,1) = max(q(i,k) / qs(i,k,1),qmin)
          sw(i,k) = (rh(i,k,1)-1.)*100.
        enddo
      enddo
!
     do k = kts,kte_in
       do i = its,ite
         qrs_tmp(i,k,1) = qrs(i,k,1)
         qrs_tmp(i,k,2) = qrs(i,k,2)
         qrs_tmp(i,k,3) = qrs(i,k,3)
         qci_tmp(i,k) = qci(i,k,2)
         nci_tmp(i,k) = nci(i,k,2)
         nrs_tmp(i,k)   = nrs(i,k,1)
       enddo
     enddo
!
   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)

   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)

      do k = kts, kte
        do i = its, ite
!-----------------------------------------------------------------
! re-compute the mean-volume drop diameter       [LH A10]
! for raindrop distribution
!-----------------------------------------------------------------
          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))
!----------------------------------------------------------------
! Nrevp_s: evaporation/condensation rate of rain   [LH A14]
!        (NR->NC)
!----------------------------------------------------------------
          if(avedia(i,k,2).le.di82) then
            nci(i,k,1) = nci(i,k,1)+nrs(i,k,1)
            nrs(i,k,1) = 0.
!----------------------------------------------------------------
! Prevp_s: evaporation/condensation rate of rain [LH A15] [KK 23]
!        (QR->QC)
!----------------------------------------------------------------
            qci(i,k,1) = qci(i,k,1)+qrs(i,k,1)
            qrs(i,k,1) = 0.
          endif
        enddo
      enddo
!
      do k = kts, kte
        do i = its, ite
!---------------------------------------------------------------
! rate of change of cloud drop concentration due to CCN activation
! pcact: QV -> QC                                 [LH 8]  [KK 14]
! ncact: NCCN -> NC                               [LH A2] [KK 12]
!---------------------------------------------------------------
           if(sw(i,k).gt.0.) then
! RH -> Si (Lei at al. 2020)
            ncact(i,k) = max(0.,((nci(i,k,3)+nci(i,k,1))                       &
                       *min(1.,(sw(i,k)/0.48)**actk) - nci(i,k,1)))/dtcld
            ncact(i,k) =min(ncact(i,k),max(nci(i,k,3),0.)/dtcld)
            pcact(i,k) = min(4.*pi*denr*(actr*1.E-6)**3*ncact(i,k)/            &
                         (3.*den(i,k)),max(q(i,k),0.)/dtcld)
            q(i,k) = max(q(i,k)-pcact(i,k)*dtcld,0.)
            qci(i,k,1) = max(qci(i,k,1)+pcact(i,k)*dtcld,0.)
            nci(i,k,3) = max(nci(i,k,3)-ncact(i,k)*dtcld,0.)
            nci(i,k,1) = max(nci(i,k,1)+ncact(i,k)*dtcld,0.)
            t(i,k) = t(i,k)+pcact(i,k)*xl(i,k)/cpm(i,k)*dtcld
          endif  
!---------------------------------------------------------------
!  pcond:condensational/evaporational rate of cloud water [HL A46] [RH83 A6]
!     if there exists additional water vapor condensated/if
!     evaporation of cloud water is not enough to remove subsaturation
!  (QV->QC or QC->QV)     
!---------------------------------------------------------------
          tr=ttp/t(i,k)
          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))
          qs(i,k,1) = max(qs(i,k,1),qmin)
          work1(i,k,1) = conden(t(i,k),q(i,k),qs(i,k,1),xl(i,k),cpm(i,k))
          work2(i,k) = qci(i,k,1)+work1(i,k,1)
          pcond(i,k) = min(max(work1(i,k,1)/dtcld,0.),max(q(i,k),0.)/dtcld)
          if(qci(i,k,1).gt.0. .and. work1(i,k,1).lt.0.)                        & 
            pcond(i,k) = max(work1(i,k,1),-qci(i,k,1))/dtcld
!----------------------------------------------------------------
! ncevp: evpration of Cloud number concentration  [LH A3] 
! (NC->NCCN) 
!----------------------------------------------------------------
          if(pcond(i,k).eq.-qci(i,k,1)/dtcld) then
            nci(i,k,3) = nci(i,k,3)+nci(i,k,1)
            nci(i,k,1) = 0.
          endif
!
          q(i,k) = q(i,k)-pcond(i,k)*dtcld
          qci(i,k,1) = max(qci(i,k,1)+pcond(i,k)*dtcld,0.)
          t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld
        enddo
      enddo
!----------------------------------------------------------------
!     padding for small values
!
      do k = kts, kte
        do i = its, ite
!20250325 v2.0
           if(qci(i,k,1).le.qmin)then
              qci(i,k,1) = 0.0
              nci(i,k,1) = 0.0
           endif
           if(qci(i,k,2).le.qmin)then
              qci(i,k,2) = 0.0
              nci(i,k,2) = 0.0
           endif
           if(qrs(i,k,1).le.qcrmin)then
              qrs(i,k,1) = 0.0
              nrs(i,k,1) = 0.0
           endif
           if(qrs(i,k,2).le.qcrmin)then
              qrs(i,k,2) = 0.0
           endif
           if(qrs(i,k,3).le.qcrmin)then
              qrs(i,k,3) = 0.0
           endif
!v2.0
!v1.0     if(qci(i,k,1).le.qmin) qci(i,k,1) = 0.0
!v1.0     if(qci(i,k,2).le.qmin) qci(i,k,2) = 0.0
          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(den(i,k)*qrs(i,k,1))))*(1./dmr))
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax 
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(den(i,k)*qci(i,k,1))))*(1./dmc))
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
            endif
          endif
          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(den(i,k)*qci(i,k,2))))*(1./dmi))
            if(lamdi_tmp(i,k) .le. lamdaimin) then
              lamdi_tmp(i,k) = lamdaimin
              nci(i,k,2) = den(i,k)*qci(i,k,2)*lamdi_tmp(i,k)**dmi/pidni
            elseif(lamdi_tmp(i,k) .ge. lamdaimax) then
              lamdi_tmp(i,k) = lamdaimax
              nci(i,k,2) = den(i,k)*qci(i,k,2)*lamdi_tmp(i,k)**dmi/pidni
            endif
          endif
            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
            if( nrs(i,k,1).gt.nrmax ) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            endif
            if( nci(i,k,1).gt.ncmax ) then
              lamdc_tmp(i,k) = lamdacmax
              nci(i,k,1) = den(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
            endif
        enddo
      enddo 
   enddo                  ! big loops
! 
   end subroutine kdm62d
!------------------------------------------------------------------------------
        REAL FUNCTION GAMMLN(x)
!------------------------------------------------------------------------------
!     --- RETURNS THE VALUE LN(GAMMA(XX)) FOR XX > 0.
      IMPLICIT NONE
      REAL :: x
      DOUBLE PRECISION, PARAMETER:: STP = 2.5066282746310005D0
      DOUBLE PRECISION, DIMENSION(6), PARAMETER:: &
               COF = (/76.18009172947146D0, -86.50532032941677D0, &
                       24.01409824083091D0, -1.231739572450155D0, &
                      .1208650973866179D-2, -.5395239384953D-5/)
      DOUBLE PRECISION:: SER,TMP,XX,Y
      INTEGER:: J

      XX=x
      Y=XX
      TMP=XX+5.5D0
      TMP=(XX+0.5D0)*LOG(TMP)-TMP
      SER=1.000000000190015D0
      DO 11 J=1,6
        Y=Y+1.D0
        SER=SER+COF(J)/Y
11    CONTINUE
      GAMMLN=TMP+LOG(STP*SER/XX)
      END FUNCTION GAMMLN
!------------------------------------------------------------------------+

      REAL function rgmma(x)
      IMPLICIT NONE
      REAL :: x

      rgmma = EXP(GAMMLN(x))

      END FUNCTION rgmma
!--------------------------------------------------------------------------
   real function fpvs(t,ice,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c)
!--------------------------------------------------------------------------
   implicit none
!--------------------------------------------------------------------------
      REAL t,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c,dldt,xa,xb,dldti,         &
           xai,xbi,ttp,tr
      INTEGER ice
! - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
      ttp=t0c+0.01
      dldt=cvap-cliq
      xa=-dldt/rv
      xb=xa+hvap/(rv*ttp)
      dldti=cvap-cice
      xai=-dldti/rv
      xbi=xai+hsub/(rv*ttp)
      tr=ttp/t
      if(t.lt.ttp .and. ice.eq.1) then
        fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
      else
        fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
      endif
! - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
      END FUNCTION fpvs
!-------------------------------------------------------------------
  SUBROUTINE kdm6init(den0,denr,dens,cl,cpv, ccn0, hail_opt, allowed_to_read) ! RAS
!-------------------------------------------------------------------
  IMPLICIT NONE
!-------------------------------------------------------------------
!.... constants which may not be tunable
   REAL, INTENT(IN) :: den0,denr,dens,cl,cpv,ccn0
   INTEGER, INTENT(IN) :: hail_opt  ! RAS
   LOGICAL, INTENT(IN) :: allowed_to_read
 
! RAS13.1 define graupel parameters as graupel-like or hail-like,
!         depending on namelist option
      IF (hail_opt .eq. 1) THEN !Hail!
         n0g       = 4.e4
         deng      = 700.
         lamdagmax = 2.e4
      ELSE !Graupel!
         n0g       = 4.e6
         deng      = 500
         lamdagmax = 1.8e5 !10micron new
        !lamdagmax = 6.e4 !16micron error
      ENDIF
!
   pi = 4.*atan(1.)
   xlv1 = cl-cpv
!
   qc0  = 4./3.*pi*denr*r0**3.*xncr0/den0
   qc1  = 4./3.*pi*denr*r0**3.*xncr1/den0
   qck1 = .104*9.8*peaut/(denr)**(1./3.)/xmyu*den0**(4./3.) ! 4706.08203
!
   bvtr1 = 1.+bvtr
   bvtr2 = 2.+bvtr
   bvtr3 = 3.+bvtr
   bvtr4 = 4.+bvtr
   bvtr5 = 5.+bvtr
   bvtr6 = 6.+bvtr
   bvtr7 = 7.+bvtr
   bvtr2o5 = 2.5+.5*bvtr
   bvtr3o5 = 2.5+.5*bvtr+mur
   drmur1 = 1.+dmr + mur
   drmur2 = 2.+dmr + mur
   drmur3 = 3.+dmr + mur
   drbrmur1 = 1.+dmr + bvtr + mur
   drbrmur3 = 3.+dmr + bvtr + mur
   brmur1 = 1.+ bvtr + mur
! 
   cmc = pi*denr/6.
   cmr = pi*denr/6.
   cms = pi*dens/6.
   cmi = pi*deni/6.
   muc1 = 1+1/(muc+1)
   muc3 = 1+3/(muc+1)
   muc4 = 1+4/(muc+1)
   muc6 = 1+6/(muc+1)
   muc9 = 1+9/(muc+1)
   g1p2dcomuc1=rgmma(1.+2*dmc/(muc+1.))
   g1pdcomuc1=rgmma(1.+dmc/(muc+1.))
   mur7 = 7.+ mur
   mur4 = 4.+ mur
   mur3 = 3.+ mur
   mur2 = 2.+ mur
   mur1 = 1.+ mur
   g1pmc = rgmma(muc1)
   g3pmc = rgmma(muc3)
   g4pmc = rgmma(muc4)
   g6pmc = rgmma(muc6)
   g9pmc = rgmma(muc9)
   g7pmr = rgmma(mur7)
   g4pmr = rgmma(mur4)
   g3pmr = rgmma(mur3)
   g2pmr = rgmma(mur2)
   g1pmr = rgmma(mur1)
   mus3 = 3.+ mus
   mus2 = 2.+ mus
   mus1 = 1.+ mus
   g3pms = rgmma(mus3)
   g2pms = rgmma(mus2)
   if (mus .eq. 0) then
      g1pms = 1. 
   else
      g1pms = rgmma(mus1)
   endif
   mug3 = 3.+ mug
   mug2 = 2.+ mug
   mug1 = 1.+ mug
   dsbsmus1 = 1.+dms + bvts + mus
   g3pmg = rgmma(mug3)
   g2pmg = rgmma(mug2)
   if (mug .eq. 0) then
      g1pmg = 1.
   else
      g1pmg = rgmma(mug1)
   endif
!!!!!!!!!!!!!!!!!!!!!!!!!!
!   pidnc = pi*denr/6.
   pidnc = cmc*rgmma(1.+dmc/(muc+1.))
   g1pdrmr = rgmma(drmur1)
   g2pdrmr = rgmma(drmur2)
   g3pdrmr = rgmma(drmur3)
   g3pbrmr = rgmma(bvtr3+mur)
   g3pdrbrmr=rgmma(drbrmur3)
   g1pdrbrmr=rgmma(drbrmur1)
   g1pbrmr=rgmma(brmur1)

   g1pbr = rgmma(bvtr1)
   g2pbr = rgmma(bvtr2)
   g3pbr = rgmma(bvtr3)
   g4pbr = rgmma(bvtr4)            ! 17.837825
   g5pbr = rgmma(bvtr5)
   g6pbr = rgmma(bvtr6)
   g7pbr = rgmma(bvtr7)
   g5pbro2 = rgmma(bvtr2o5) 
   g7pbro2 = rgmma(bvtr3o5)
   g1p2drmr = rgmma(drmur1+dmr)
!   pvtr = avtr*g5pbr/24.
   pvtr = avtr*g1pdrbrmr/g1pdrmr
!   pvtrn = avtr*g2pbr
   pvtrn = avtr*g1pbrmr/g1pmr
   eacrr = 1.0
!   pacrr = pi*n0r*avtr*g3pbr*.25*eacrr
!   precr1 = 2.*pi*1.56
   precr1 = 2.*pi*0.78*g2pmr
   precr2 = 2.*pi*.31*avtr**.5*g7pbro2
!   pidn0r =  pi*denr*n0r
!   pidnr = 4.*pi*denr
   pidnr =  cmr*g1pdrmr/g1pmr

!
   xmmax = (dimax/dicon)**2
   roqimax = 2.08e22*dimax**8
!
   mui1 = 1. + mui
   mui2 = 2. + mui
   mui3 = 3. + mui
   mui4 = 4. + mui
   mui5 = 5. + mui
   g1pmi = rgmma(mui1)
   g2pmi = rgmma(mui2)
   g3pmi = rgmma(mui3)
   g4pmi = rgmma(mui4)
   g5pmi = rgmma(mui5)
   dibimui1 = 1.+dmi + bvti + mui       
   bimui1 = 1.+ bvti + mui      
   dimui1 = 1.+dmi + mui
   dimui2 = 2.+dmi + mui
   dimui3 = 3.+dmi + mui
   g1pbimi =rgmma(bimui1)
   g1pdibimi=rgmma(dibimui1)
   g1pdimi = rgmma(dimui1)
   g2pdimi = rgmma(dimui2)
   g3pdimi = rgmma(dimui3)
   pvti = avti*g1pdibimi/g1pdimi
   pvtin = avti*g1pbimi/g1pmi
   pidni = cmi*g1pdimi/g1pmi
!
   dsmus1 = 1.+dms + mus
   dsmus2 = 2.+dms + mus
   dsmus3 = 3.+dms + mus
   g1pdsms = rgmma(dsmus1)
   g2pdsms = rgmma(dsmus2)
   g3pdsms = rgmma(dsmus3)
   g1pdsbsms=rgmma(dsbsmus1)
   bvts1 = 1.+bvts
   bvts2 = 2.5+.5*bvts+mus
   bvti3 = 3.+bvti+mui
   g3pbi = rgmma(bvti3)
   bvts3 = 3.+bvts+mus
   bvts4 = 4.+bvts
   g1pbs = rgmma(bvts1)    !.8875
   g3pbs = rgmma(bvts3)
   g4pbs = rgmma(bvts4)    ! 12.0786
   g5pbso2 = rgmma(bvts2)
!   pvts = avts*g4pbs/6.
   pvts = avts*g1pdsbsms/g1pdsms
!   precs1 = 4.*n0s*.65
!   precs2 = 4.*n0s*.44*avts**.5*g5pbso2
   precs1 = 4.*.65*g2pms
   precs2 = 4.*.44*avts**.5*g5pbso2
!   pidn0s =  pi*dens*n0s
   pidn0s =  cms*n0s*g1pdsms/g1pms
!
!   pacrc = pi*n0s*avts*g3pbs*.25*eacsc
!
   dgmug1 = 1.+dmg + mug
   g1pdgmg = rgmma(dgmug1)
   precg1 = 4.*.78*g2pmg
!
   rslopecmax = 1./lamdacmax
   rslopermax = 1./lamdarmax
   rslopesmax = 1./lamdasmax
   rslopegmax = 1./lamdagmax
   rslopeimax = 1./lamdaimax
   rslopecmmax = DBLE(rslopecmax) ** muc
   rslopermmax = DBLE(rslopermax) ** mur
   if (mus .ne. 0) then
   rslopesmmax = DBLE(rslopesmax) ** mus
   else
   rslopesmmax = 1.
   endif
   if (mug .ne. 0) then
   rslopegmmax = DBLE(rslopegmax) ** mug
   else
   rslopegmmax = 1. 
   endif
   if (mui .ne. 0) then
   rslopeimmax = DBLE(rslopeimax) ** mui
   else
   rslopeimmax = 1.
   endif
!   if (muh .ne. 0) then
!   rslopehmmax = rslopehmax ** muh
!   else
!   rslopehmmax = 1.
!   endif
   rsloperbmax = rslopermax ** bvtr
   rslopesbmax = rslopesmax ** bvts
   rsloperdmax = (rslopermax) ** dmr
   rslopesdmax = (rslopesmax) ** dms
   rslopegdmax = (rslopegmax) ** dmg
   rslopec2max = (rslopecmax) * rslopecmax
   rsloper2max = (rslopermax) * rslopermax
   rslopes2max = (rslopesmax) * rslopesmax
   rslopeg2max = (rslopegmax) * rslopegmax
   rslopec3max = (rslopec2max) * rslopecmax
   rsloper3max = (rsloper2max) * rslopermax
   rslopes3max = (rslopes2max) * rslopesmax
   rslopeg3max = (rslopeg2max) * rslopegmax
   rslopeibmax = rslopeimax ** bvti
   rslopeidmax = (rslopeimax) ** dmi
   rslopei2max = (rslopeimax) * rslopeimax
   rslopei3max = (rslopei2max) * rslopeimax
!+---+-----------------------------------------------------------------+
!..Set these variables needed for computing radar reflectivity.  These
!.. get used within radar_init to create other variables used in the
!.. radar module.
   xam_c = cmc
   xbm_c = dmc
   xmu_c = muc
   xam_r = cmr 
   xbm_r = dmr 
   xmu_r = mur 
   xam_s = cms 
   xbm_s = dms 
   xmu_s = mus 
   xbm_g = dmg 
   xmu_g = mug 
   xam_i = cmi
   xbm_i = dmi
   xmu_i = mui
   call radar_init
!+---+-----------------------------------------------------------------+
!
  END SUBROUTINE kdm6init
!------------------------------------------------------------------------------
   SUBROUTINE ProgB_param(brs,qrs,rhox,its,ite,jts,jte,kts,kte,qcrmin             &
                         ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2&
                         ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax     &
                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)
  implicit none
  integer           :: i,k,sy, its,ite, jts,jte, kts,kte
  real, intent(in)  ::qcrmin,dmg,mug,pi
  real, intent(in)  ::g1pdgmg,g1pmg,n0g
  real, intent(in)  ::rslopegmax
  REAL, DIMENSION( its:ite , kts:kte,3), INTENT(IN) :: qrs
  REAL, DIMENSION( its:ite , kts:kte), INTENT(INOUT):: brs   !prognosticparameter
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox    !diagnosticparameter
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&
                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1
  REAL ::tmp1,tmp2
  real,dimension(9) :: Tbl,aTbl,bTbl
  real, parameter   :: rho_min = 100.      !kg m-3,  minimum allowabale graupel density
  real, parameter   :: rho_max = 900.      !kg m-3,  maximum allowabale graupel density
  real, parameter   :: rho_mid = 400.      !kg m-3,  default graupel density
  real, parameter   :: brs_min = 1.e-15   !m3 kg-1, min.allowable bulk volume mixing ratio

 !  using the parameters corresponding to the nearested densities.
  data Tbl /    100.,   200.,   300.,   400.,   500.,   600.,   700., 800., 900./   !deg
  data aTbl   /  54.9153,   74.2262,   88.8313,  101.0411, 111.7359,  121.3625, 130.1841,  138.3714, 146.0422 / !a(deg)
  data bTbl   / 0.5446,    0.5375,    0.5339,    0.5316, 0.5299,    0.5286, 0.5275,    0.5266, 0.5258 / !b(deg)
 !==

      do k = kts, kte
        do i = its, ite


     if (qrs(i,k,3).gt. qcrmin .or. brs(i,k).gt. brs_min) then

         rhox(i,k) = qrs(i,k,3)/brs(i,k)

         if (rhox(i,k) .lt. rho_min .or. rhox(i,k) .gt. rho_max) then
          rhox(i,k) = min(rho_max,max(rho_min,rhox(i,k)))
         else
          rhox(i,k) = rhox(i,k)
         endif

        if (rhox(i,k).ge. rho_min .and. rhox(i,k).le. rho_max) then
        brs(i,k)  = qrs(i,k,3)/rhox(i,k)
        cmg(i,k) = pi*rhox(i,k)/6
        pidn0g(i,k) =  cmg(i,k)*n0g*g1pdgmg/g1pmg
        endif
      endif
         if (cmg(i,k).gt. 0) then
          if (rhox(i,k).ge. Tbl(1) .and. rhox(i,k).lt.Tbl(9)) then
                  do sy = 1,8
                   if (Tbl(sy).le. rhox(i,k) .and. Tbl(sy+1).gt.rhox(i,k)) then
                   tmp2 = 1./(Tbl(sy+1)-Tbl(sy))
                   avtg(i,k)=aTbl(sy)+(rhox(i,k)-Tbl(sy))*(aTbl(sy+1)-aTbl(sy))*tmp2
                   bvtg(i,k)=bTbl(sy)+(rhox(i,k)-Tbl(sy))*(bTbl(sy+1)-bTbl(sy))*tmp2
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
                   exit
                   endif
                  enddo
         else if (rhox(i,k).eq. Tbl(9)) then
                   avtg(i,k)=aTbl(9)
                   bvtg(i,k)=bTbl(9)
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
         endif
       endif
      enddo
    enddo

  END subroutine ProgB_param
!------------------------------------------------------------------------------
      subroutine slope_kdm6(qrs,qci,nrs,nci,den,denfac,t,rslope,rslopeb,rslope2,rslope3, &
                            rslopemu,rsloped,vt,vtn,its,ite,kts,kte,qmin,pidn0g,         &
                            pvtg,bvtg,rslopegbmax)
  IMPLICIT NONE
  INTEGER       ::               its,ite, jts,jte, kts,kte


  REAL, DIMENSION( its:ite , kts:kte,3) ::   qrs                                 
  REAL, DIMENSION( its:ite , kts:kte) ::   qci
  REAL, DIMENSION( its:ite , kts:kte) :: nci,nrs
  REAL, DIMENSION( its:ite , kts:kte,4) ::                            rslope,  &
                                                                      rslopeb, &
                                                                      rsloped, &
                                                                      rslope2, &
                                                                      rslope3

 
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte,4) ::            vt,rslopemu
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte,2) ::                   vtn
  REAL, DIMENSION( its:ite , kts:kte) ::                                       &  
                                                                          den, &
                                                                       denfac, &
                                                                       t,n0sfac

  REAL, INTENT(IN) :: qmin
  REAL, PARAMETER  :: t0c = 273.15
  REAL       ::  lamdas, lamdag, x, y, z, supcol
  REAL       ::  lamdar,lamdai
  integer :: i, j, k
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::pidn0g
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::pvtg
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::bvtg,rslopegbmax
!----------------------------------------------------------------
!     size distributions: (x=mixing ratio, y=air density):
!     valid for mixing ratio > 1.e-9 kg/kg.
!
!  Optimizatin : A**B => exp(log(A)*(B))
! revised
!      lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*((.33333333)))
!     lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*(1./dmr))
      lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*(1./dmr)) 
!      lamdas(x,y,z)= sqrt(sqrt(pidn0s*z/(x*y)))    ! (pidn0s*z/(x*y))**.25
      lamdas(x,y,z)= exp(log(((pidn0s*z)/(x*y)))*(1./(dms+1)))
!      lamdag(x,y)=   sqrt(sqrt(pidn0g/(x*y)))      ! (pidn0g/(x*y))**.25
      lamdag(x,y)= exp(log(((pidn0g(i,k))/(x*y)))*(1./(dmg+1)))
!
      lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))
!
      do k = kts, kte
        do i = its, ite
          supcol = t0c-t(i,k)
!---------------------------------------------------------------
! n0s: Intercept parameter for snow [m-4] [HDC 6]
!---------------------------------------------------------------
          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          if(qrs(i,k,1).le.qcrmin .or. nrs(i,k).le.nrmin ) then
            rslope(i,k,1) = rslopermax
            rslopeb(i,k,1) = rsloperbmax
            rslopemu(i,k,1) = rslopermmax
            rsloped(i,k,1) = rsloperdmax
            rslope2(i,k,1) = rsloper2max
            rslope3(i,k,1) = rsloper3max
          else
            rslope(i,k,1) = min(1./lamdar(qrs(i,k,1),den(i,k),nrs(i,k)),1.e-3)
            rslopeb(i,k,1) = (rslope(i,k,1))**bvtr
            rslopemu(i,k,1) = DBLE(rslope(i,k,1))**mur
            rsloped(i,k,1) = (rslope(i,k,1))**dmr
            rslope2(i,k,1) = (rslope(i,k,1))*rslope(i,k,1)
            rslope3(i,k,1) = (rslope2(i,k,1))*rslope(i,k,1)
          endif
          if(qrs(i,k,2).le.qcrmin) then
            rslope(i,k,2) = rslopesmax
            rslopeb(i,k,2) = rslopesbmax
            rslopemu(i,k,2) = rslopesmmax
            rsloped(i,k,2) = rslopesdmax
            rslope2(i,k,2) = rslopes2max
            rslope3(i,k,2) = rslopes3max
          else
            rslope(i,k,2) = 1./lamdas(qrs(i,k,2),den(i,k),n0sfac(i,k))
            rslopeb(i,k,2) = (rslope(i,k,2))**bvts
            rslopemu(i,k,2) = DBLE(rslope(i,k,2))**mus
            rsloped(i,k,2) = (rslope(i,k,2))**dms
            rslope2(i,k,2) = (rslope(i,k,2))*rslope(i,k,2)
            rslope3(i,k,2) = (rslope2(i,k,2))*rslope(i,k,2)
          endif
          if(qrs(i,k,3).le.qcrmin) then
            rslope(i,k,3) = rslopegmax
            rslopeb(i,k,3) = rslopegbmax(i,k)
            rslopemu(i,k,3) = rslopegmmax
            rsloped(i,k,3) = rslopegdmax
            rslope2(i,k,3) = rslopeg2max
            rslope3(i,k,3) = rslopeg3max
          else
            rslope(i,k,3) = 1./lamdag(qrs(i,k,3),den(i,k))
            rslopeb(i,k,3) = (rslope(i,k,3))**bvtg(i,k)
            rslopemu(i,k,3) = DBLE(rslope(i,k,3))**mug
            rsloped(i,k,3) = (rslope(i,k,3))**dmg
            rslope2(i,k,3) = (rslope(i,k,3))*rslope(i,k,3)
            rslope3(i,k,3) = (rslope2(i,k,3))*rslope(i,k,3)
          endif
          if(qci(i,k) .le. qmin) then  
            rslope(i,k,4) = rslopeimax
            rslopeb(i,k,4) = rslopeibmax
            rslopemu(i,k,4) = rslopeimmax
            rsloped(i,k,4) = rslopeidmax
            rslope2(i,k,4) = rslopei2max
            rslope3(i,k,4) = rslopei3max
          else
           rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &
                          1./lamdaimax)
            rslopeb(i,k,4) = (rslope(i,k,4))**bvti
            rslopemu(i,k,4) = DBLE(rslope(i,k,4))**mui
            rsloped(i,k,4) = (rslope(i,k,4))**dmi
            rslope2(i,k,4) = (rslope(i,k,4))*rslope(i,k,4)
            rslope3(i,k,4) = (rslope2(i,k,4))*rslope(i,k,4)
          endif
          vt(i,k,1) = DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
          vt(i,k,2) = DBLE(pvts)*rslopeb(i,k,2)*denfac(i,k)
          vt(i,k,3) = DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)
          vt(i,k,4) = DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          if(qrs(i,k,1).le.0.0) vt(i,k,1) = 0.0 
          if(qrs(i,k,2).le.0.0) vt(i,k,2) = 0.0
          if(qrs(i,k,3).le.0.0) vt(i,k,3) = 0.0
          if(qci(i,k).le.0.0) vt(i,k,4) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k,1) = 0.0 
          if(nci(i,k).le.0.0) vtn(i,k,2) = 0.0 
          vtn(i,k,1) = DBLE(pvtrn)*rslopeb(i,k,1)*denfac(i,k)
          vtn(i,k,2) = DBLE(pvtin)*rslopeb(i,k,4)*denfac(i,k) 
        enddo
      enddo
  END subroutine slope_kdm6
!-----------------------------------------------------------------------------
      subroutine slope_rain(qrs,nrs,den,denfac,t,rslope,rslopeb,rslope2,rslope3,   &
                            rsloped,rslopemu,vt,vtn,its,ite,kts,kte)
  IMPLICIT NONE
  INTEGER       ::               its,ite, jts,jte, kts,kte
  REAL, DIMENSION( its:ite , kts:kte) ::                                  qrs, &
                                                                          den, &
                                                                       denfac, &
                                                                            t
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte) ::          vt,vtn,rslopemu
  REAL, DIMENSION( its:ite , kts:kte) ::                                  nrs, &
                                                                       rslope, &
                                                                      rslopeb, &
                                                                      rsloped, &
                                                                      rslope2, &
                                                                      rslope3
  REAL, PARAMETER  :: t0c = 273.15
  REAL, DIMENSION( its:ite , kts:kte ) ::                                      &
                                                                       n0sfac
  REAL       ::  x, y, z, supcol
  REAL       ::  lamdar, xd, yd, zd
  integer :: i, j, k
!----------------------------------------------------------------
!     size distributions: (x=mixing ratio, y=air density):
!     valid for mixing ratio > 1.e-9 kg/kg.
!      lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*((.33333333)))
      lamdar(xd,yd,zd)= exp(log(((pidnr*zd)/(xd*yd)))*(1./dmr))
!
      do k = kts, kte
        do i = its, ite
          if(qrs(i,k).le.qcrmin .or. nrs(i,k).le.nrmin) then
            rslope(i,k) = rslopermax
            rslopeb(i,k) = rsloperbmax
            rslopemu(i,k) = rslopermmax
            rslope2(i,k) = rsloper2max
            rslope3(i,k) = rsloper3max
          else
            rslope(i,k) = min(1./lamdar(qrs(i,k),den(i,k),nrs(i,k)),1.e-3)
            rslopeb(i,k) = (rslope(i,k))**bvtr
            rslopemu(i,k) = DBLE(rslope(i,k))**mur
            rsloped(i,k) = (rslope(i,k))**dmr
            rslope2(i,k) = (rslope(i,k))*rslope(i,k)
            rslope3(i,k) = (rslope2(i,k))*rslope(i,k)
          endif
          vt(i,k) = DBLE(pvtr)*rslopeb(i,k)*denfac(i,k)
          vtn(i,k) = DBLE(pvtrn)*rslopeb(i,k)*denfac(i,k)
          if(qrs(i,k).le.0.0) vt(i,k) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k) = 0.0 
        enddo
      enddo
  END subroutine slope_rain
!------------------------------------------------------------------------------
      SUBROUTINE nislfv_rain_plmr(im,km,denl,denfacl,tkl,dzl,wwl,rql,rnl,precip,dt,id,iter,rid)
!-------------------------------------------------------------------
!
! for non-iteration semi-Lagrangain forward advection for cloud
! with mass conservation and positive definite advection
! 2nd order interpolation with monotonic piecewise linear method
! this routine is under assumption of decfl < 1 for semi_Lagrangian
!
! dzl    depth of model layer in meter
! wwl    terminal velocity at model layer m/s
! rql    cloud density*mixing ration
! precip precipitation
! dt     time step
! id     kind of precip: 0 test case; 1 raindrop
! iter   how many time to guess mean terminal velocity: 0 pure forward.
!        0 : use departure wind for advection
!        1 : use mean wind for advection
!        > 1 : use mean wind after iter-1 iterations
!        rid : 1 for number 0 for mixing ratio
!
! author: hann-ming henry juang <henry.juang@noaa.gov>
!         implemented by song-you hong
!
      implicit none
      integer  im,km,id
      real  dt
      real  dzl(im,km),wwl(im,km),rql(im,km),rnl(im,km),precip(im)
      real  denl(im,km),denfacl(im,km),tkl(im,km)
!
      integer  i,k,n,m,kk,kb,kt,iter,rid
      real  tl,tl2,qql,dql,qqd
      real  th,th2,qqh,dqh
      real  zsum,qsum,dim,dip,c1,con1,fa1,fa2
      real  allold, allnew, zz, dzamin, cflmax, decfl
      real  dz(km), ww(km), qq(km), wd(km), was(km)
      real  den(km), denfac(km), tk(km)
      real  wi(km+1), zi(km+1), za(km+1)
      real  qn(km), qr(km), qr2(km)
      real tmp(km),tmp1(km),tmp2(km),tmp3(km),tmp4(km),nr(km)
      double precision wa(km),wa2(km), tmp5(km)
      real  dza(km+1), qa(km+1), qmi(km+1), qpi(km+1)
!
      precip(:) = 0.0
!
      i_loop : do i=1,im
! -----------------------------------
      dz(:) = dzl(i,:)
      qq(:) = rql(i,:)
      nr(:) = rnl(i,:)
      if(rid .eq. 1) nr(:) = rnl(i,:)/denl(i,:)
      ww(:) = wwl(i,:)
      den(:) = denl(i,:)
      denfac(:) = denfacl(i,:)
      tk(:) = tkl(i,:)
! skip for no precipitation for all layers
      allold = 0.0
      do k=1,km
        allold = allold + qq(k)
      enddo
      if(allold.le.0.0) then
        cycle i_loop
      endif
!
! compute interface values
      zi(1)=0.0
      do k=1,km
        zi(k+1) = zi(k)+dz(k)
      enddo
!
! save departure wind
      wd(:) = ww(:)
      n=1
 100  continue
! plm is 2nd order, we can use 2nd order wi or 3rd order wi
! 2nd order interpolation to get wi
      wi(1) = ww(1)
      wi(km+1) = ww(km)
      do k=2,km
        wi(k) = (ww(k)*dz(k-1)+ww(k-1)*dz(k))/(dz(k-1)+dz(k))
      enddo
! 3rd order interpolation to get wi
      fa1 = 9./16.
      fa2 = 1./16.
      wi(1) = ww(1)
      wi(2) = 0.5*(ww(2)+ww(1))
      do k=3,km-1
        wi(k) = fa1*(ww(k)+ww(k-1))-fa2*(ww(k+1)+ww(k-2))
      enddo
      wi(km) = 0.5*(ww(km)+ww(km-1))
      wi(km+1) = ww(km)
!
! terminate of top of raingroup
      do k=2,km
        if( ww(k).eq.0.0 ) wi(k)=ww(k-1)
      enddo
!
! diffusivity of wi
      con1 = 0.05
      do k=km,1,-1
        decfl = (wi(k+1)-wi(k))*dt/dz(k)
        if( decfl .gt. con1 ) then
          wi(k) = wi(k+1) - con1*dz(k)/dt
        endif
      enddo
! compute arrival point
      do k=1,km+1
        za(k) = zi(k) - wi(k)*dt
      enddo
!
      do k=1,km
        dza(k) = za(k+1)-za(k)
      enddo
      dza(km+1) = zi(km+1) - za(km+1)
!     
! computer deformation at arrival point
      do k=1,km
        qa(k) = qq(k)*dz(k)/dza(k)
        qr(k) = qa(k)/den(k)
        if(rid .eq. 1) qr(k) = qa(K)
      enddo
      qa(km+1) = 0.0
!     call maxmin(km,1,qa,' arrival points ')
!     
! compute arrival terminal velocity, and estimate mean terminal velocity
! then back to use mean terminal velocity
      if( n.le.iter ) then
        if(rid.eq.1) then
        call slope_rain(qr,nr,den,denfac,tk,tmp,tmp1,tmp2,tmp3,tmp4,tmp5,wa,wa2,1,1,1,km)
        else
        call slope_rain(qr,nr,den,denfac,tk,tmp,tmp1,tmp2,tmp3,tmp4,tmp5,wa,wa2,1,1,1,km)
        endif
        if(rid.eq.1) wa(:) = wa2(:)
        if( n.ge.2 ) wa(1:km)=0.5*(wa(1:km)+was(1:km))
        do k=1,km
!#ifdef DEBUG 
!        print*,' slope_wsm3 ',qr(k)*1000.,den(k),denfac(k),tk(k),tmp(k),tmp1(k),tmp2(k),ww(k),wa(k)
!#endif
! mean wind is average of departure and new arrival winds
          ww(k) = 0.5* ( wd(k)+wa(k) )
        enddo
        was(:) = wa(:)
        n=n+1
        go to 100
      endif
!     
! estimate values at arrival cell interface with monotone
      do k=2,km
        dip=(qa(k+1)-qa(k))/(dza(k+1)+dza(k))
        dim=(qa(k)-qa(k-1))/(dza(k-1)+dza(k))
        if( dip*dim.le.0.0 ) then
          qmi(k)=qa(k)
          qpi(k)=qa(k)
        else
          qpi(k)=qa(k)+0.5*(dip+dim)*dza(k)
          qmi(k)=2.0*qa(k)-qpi(k)
          if( qpi(k).lt.0.0 .or. qmi(k).lt.0.0 ) then
            qpi(k) = qa(k)
            qmi(k) = qa(k)
          endif
        endif
      enddo
      qpi(1)=qa(1)
      qmi(1)=qa(1)
      qmi(km+1)=qa(km+1)
      qpi(km+1)=qa(km+1)
!
! interpolation to regular point
      qn = 0.0
      kb=1
      kt=1
      intp : do k=1,km
             kb=max(kb-1,1)
             kt=max(kt-1,1)
! find kb and kt
             if( zi(k).ge.za(km+1) ) then
               exit intp
             else
               find_kb : do kk=kb,km
                         if( zi(k).le.za(kk+1) ) then
                           kb = kk
                           exit find_kb
                         else
                           cycle find_kb
                         endif
               enddo find_kb
               find_kt : do kk=kt,km
                         if( zi(k+1).le.za(kk) ) then
                           kt = kk
                           exit find_kt
                         else
                           cycle find_kt
                         endif
               enddo find_kt
               kt = kt - 1
! compute q with piecewise constant method
               if( kt.eq.kb ) then
                 tl=(zi(k)-za(kb))/dza(kb)
                 th=(zi(k+1)-za(kb))/dza(kb)
                 tl2=tl*tl
                 th2=th*th
                 qqd=0.5*(qpi(kb)-qmi(kb))
                 qqh=qqd*th2+qmi(kb)*th
                 qql=qqd*tl2+qmi(kb)*tl
                 qn(k) = (qqh-qql)/(th-tl)
               else if( kt.gt.kb ) then
                 tl=(zi(k)-za(kb))/dza(kb)
                 tl2=tl*tl
                 qqd=0.5*(qpi(kb)-qmi(kb))
                 qql=qqd*tl2+qmi(kb)*tl
                 dql = qa(kb)-qql
                 zsum  = (1.-tl)*dza(kb)
                 qsum  = dql*dza(kb)
                 if( kt-kb.gt.1 ) then
                 do m=kb+1,kt-1
                   zsum = zsum + dza(m)
                   qsum = qsum + qa(m) * dza(m)
                 enddo
                 endif
                 th=(zi(k+1)-za(kt))/dza(kt)
                 th2=th*th
                 qqd=0.5*(qpi(kt)-qmi(kt))
                 dqh=qqd*th2+qmi(kt)*th
                 zsum  = zsum + th*dza(kt)
                 qsum  = qsum + dqh*dza(kt)
                 qn(k) = qsum/zsum
               endif
               cycle intp
             endif
!     
       enddo intp
!            
! rain out
      sum_precip: do k=1,km
                    if( za(k).lt.0.0 .and. za(k+1).lt.0.0 ) then
                      precip(i) = precip(i) + qa(k)*dza(k)
                      cycle sum_precip
                    else if ( za(k).lt.0.0 .and. za(k+1).ge.0.0 ) then
                      precip(i) = precip(i) + qa(k)*(0.0-za(k))
                      exit sum_precip
                    endif
                    exit sum_precip
      enddo sum_precip
!              
! replace the new values 
      rql(i,:) = qn(:)     
!                          
! ----------------------------------
      enddo i_loop         
!                        
  END SUBROUTINE nislfv_rain_plmr
!-------------------------------------------------------------------
!+---+-----------------------------------------------------------------+
      subroutine refl10cm_kdm6 (qv1d, qr1d, nr1d, qs1d, qg1d, n0so1d,            &
                       n0go1d, t1d, p1d, dBZ, kts, kte, ii, jj,xam_g)
      IMPLICIT NONE
      REAL, DIMENSION(kts:kte), INTENT(IN):: xam_g
!..Sub arguments
      INTEGER, INTENT(IN):: kts, kte, ii, jj
      REAL, DIMENSION(kts:kte), INTENT(IN)::                            &
                      qv1d, qr1d, nr1d, qs1d, qg1d, t1d, p1d
      real, DIMENSION(kts:kte), INTENT(IN)::  n0so1d, n0go1d
      REAL, DIMENSION(kts:kte), INTENT(INOUT):: dBZ

!..Local variables
      REAL, DIMENSION(kts:kte):: temp, pres, qv, rho
      REAL, DIMENSION(kts:kte):: rr, nr, rs, rg
      REAL:: temp_C

      DOUBLE PRECISION, DIMENSION(kts:kte):: ilamr, ilams, ilamg
      DOUBLE PRECISION, DIMENSION(kts:kte):: N0_r, N0_s, N0_g
      DOUBLE PRECISION:: lamr, lams, lamg
      LOGICAL, DIMENSION(kts:kte):: L_qr, L_qs, L_qg

      REAL, DIMENSION(kts:kte):: ze_rain, ze_snow, ze_graupel
      DOUBLE PRECISION:: fmelt_s, fmelt_g

      INTEGER:: i, k, k_0, kbot, n
      LOGICAL:: melti

      DOUBLE PRECISION:: cback, x, eta, f_d
      REAL, PARAMETER:: R=287.

!+---+

      do k = kts, kte
         dBZ(k) = -35.0
      enddo

!+---+-----------------------------------------------------------------+
!..Put column of data into local arrays.
!+---+-----------------------------------------------------------------+
      do k = kts, kte
         temp(k) = t1d(k)
         temp_C = min(-0.001, temp(K)-273.15)
         qv(k) = MAX(1.E-10, qv1d(k))
         pres(k) = p1d(k)
         rho(k) = 0.622*pres(k)/(R*temp(k)*(qv(k)+0.622))

         if (qr1d(k) .gt. 1.E-9) then
            rr(k) = qr1d(k)*rho(k)
            nr(k) = nr1d(k)*rho(k)
            lamr = (xam_r*xcrg(3)*xorg2*nr(k)/rr(k))**xobmr
            ilamr(k) = 1./lamr
            N0_r(k) = nr(k)*xorg2*lamr**xcre(2)
            L_qr(k) = .true.
         else
            rr(k) = 1.E-12
            nr(k) = 1.E-12
            L_qr(k) = .false.
         endif

         if (qs1d(k) .gt. 1.E-9) then
            rs(k) = qs1d(k)*rho(k)
            N0_s(k) = min(n0smax, n0so1d(k)*exp(-alpha*temp_C))
            lams = (xam_s*xcsg(3)*N0_s(k)/rs(k)/xcsg(2))**(1./xcse(1))
!            lams = (xam_s*xcsg(3)*N0_s(k)/rs(k))**(1./xcse(1))
            ilams(k) = 1./lams
            L_qs(k) = .true.
         else
            rs(k) = 1.E-12
            L_qs(k) = .false.
         endif

         if (qg1d(k) .gt. 1.E-9) then
            rg(k) = qg1d(k)*rho(k)
            N0_g(k) = n0go1d(k)
!            lamg = (xam_g*xcgg(3)*N0_g(k)/rg(k))**(1./xcge(1))
            lamg = (xam_g(k)*xcgg(3)*N0_g(k)/rg(k)/xcgg(2))**(1./xcge(1))
            ilamg(k) = 1./lamg
            L_qg(k) = .true.
         else
            rg(k) = 1.E-12
            L_qg(k) = .false.
         endif
      enddo

!+---+-----------------------------------------------------------------+
!..Locate K-level of start of melting (k_0 is level above).
!+---+-----------------------------------------------------------------+
      melti = .false.
      k_0 = kts
      do k = kte-1, kts, -1
         if ( (temp(k).gt.273.15) .and. L_qr(k)                         &
                                  .and. (L_qs(k+1).or.L_qg(k+1)) ) then
            k_0 = MAX(k+1, k_0)
            melti=.true.
            goto 195
         endif
      enddo
 195  continue

!+---+-----------------------------------------------------------------+
!..Assume Rayleigh approximation at 10 cm wavelength. Rain (all temps)
!.. and non-water-coated snow and graupel when below freezing are
!.. simple. Integrations of m(D)*m(D)*N(D)*dD.
!+---+-----------------------------------------------------------------+

      do k = kts, kte
         ze_rain(k) = 1.e-22
         ze_snow(k) = 1.e-22
         ze_graupel(k) = 1.e-22
         if (L_qr(k)) ze_rain(k) = N0_r(k)*xcrg(4)*ilamr(k)**xcre(4)
         if (L_qs(k)) ze_snow(k) = (0.176/0.93) * (6.0/PI)*(6.0/PI)     &
                                 * (xam_s/900.0)*(xam_s/900.0)          &
                                 * N0_s(k)*xcsg(4)*ilams(k)**xcse(4)
         if (L_qg(k)) ze_graupel(k) = (0.176/0.93) * (6.0/PI)*(6.0/PI)  &
                                    * (xam_g(k)/900.0)*(xam_g(k)/900.0)       &
                                    * N0_g(k)*xcgg(4)*ilamg(k)**xcge(4)
      enddo


!+---+-----------------------------------------------------------------+
!..Special case of melting ice (snow/graupel) particles.  Assume the
!.. ice is surrounded by the liquid water.  Fraction of meltwater is
!.. extremely simple based on amount found above the melting level.
!.. Uses code from Uli Blahak (rayleigh_soak_wetgraupel and supporting
!.. routines).
!+---+-----------------------------------------------------------------+

      if (melti .and. k_0.ge.kts+1) then
       do k = k_0-1, kts, -1

!..Reflectivity contributed by melting snow
          if (L_qs(k) .and. L_qs(k_0) ) then
           fmelt_s = MAX(0.005d0, MIN(1.0d0-rs(k)/rs(k_0), 0.99d0))
           eta = 0.d0
           lams = 1./ilams(k)
           do n = 1, nrbins
              x = xam_s * xxDs(n)**xbm_s
              call rayleigh_soak_wetgraupel (x,DBLE(xocms),DBLE(xobms), &
                    fmelt_s, melt_outside_s, m_w_0, m_i_0, lamda_radar, &
                    CBACK, mixingrulestring_s, matrixstring_s,          &
                    inclusionstring_s, hoststring_s,                    &
                    hostmatrixstring_s, hostinclusionstring_s)
              f_d = N0_s(k)*xxDs(n)**xmu_s * DEXP(-lams*xxDs(n))
              eta = eta + f_d * CBACK * simpson(n) * xdts(n)
           enddo
           ze_snow(k) = SNGL(lamda4 / (pi5 * K_w) * eta)
          endif


!..Reflectivity contributed by melting graupel

          if (L_qg(k) .and. L_qg(k_0) ) then
           fmelt_g = MAX(0.005d0, MIN(1.0d0-rg(k)/rg(k_0), 0.99d0))
           eta = 0.d0
           lamg = 1./ilamg(k)
           do n = 1, nrbins
              x = xam_g(k) * xxDg(n)**xbm_g
              call rayleigh_soak_wetgraupel (x,DBLE(xocmg),DBLE(xobmg), &
                    fmelt_g, melt_outside_g, m_w_0, m_i_0, lamda_radar, &
                    CBACK, mixingrulestring_g, matrixstring_g,          &
                    inclusionstring_g, hoststring_g,                    &
                    hostmatrixstring_g, hostinclusionstring_g)
              f_d = N0_g(k)*xxDg(n)**xmu_g * DEXP(-lamg*xxDg(n))
              eta = eta + f_d * CBACK * simpson(n) * xdtg(n)
           enddo
           ze_graupel(k) = SNGL(lamda4 / (pi5 * K_w) * eta)
          endif

       enddo
      endif

      do k = kte, kts, -1
         dBZ(k) = 10.*log10((ze_rain(k)+ze_snow(k)+ze_graupel(k))*1.d18)
      enddo


      end subroutine refl10cm_kdm6
!+---+-----------------------------------------------------------------+

!-----------------------------------------------------------------------
     subroutine effectRad_kdm6 (t, qc, nc, qi, ni, qs, rho, qmin, t0c,    &
                                re_qc, re_qi, re_qs, kts, kte, ii, jj)

!-----------------------------------------------------------------------
!  Compute radiation effective radii of cloud water, ice, and snow for 
!  double-moment microphysics..
!  These are entirely consistent with microphysics assumptions, not
!  constant or otherwise ad hoc as is internal to most radiation
!  schemes.  
!  Coded and implemented by Soo Ya Bae, KIAPS, January 2015.
!-----------------------------------------------------------------------

      implicit none

!..Sub arguments
      integer, intent(in) :: kts, kte, ii, jj
      real, intent(in) :: qmin
      real, intent(in) :: t0c
      real, dimension( kts:kte ), intent(in)::  t
      real, dimension( kts:kte ), intent(in)::  qc
      real, dimension( kts:kte ), intent(in)::  nc
      real, dimension( kts:kte ), intent(in)::  ni
      real, dimension( kts:kte ), intent(in)::  qi
      real, dimension( kts:kte ), intent(in)::  qs
      real, dimension( kts:kte ), intent(in)::  rho
      real, dimension( kts:kte ), intent(inout):: re_qc
      real, dimension( kts:kte ), intent(inout):: re_qi
      real, dimension( kts:kte ), intent(inout):: re_qs
!..Local variables
      integer:: i,k
      integer :: inu_c
      real, dimension( kts:kte ):: rqc
      real, dimension( kts:kte ):: rnc
      real, dimension( kts:kte ):: rqi
      real, dimension( kts:kte ):: rni
      real, dimension( kts:kte ):: rqs
      real :: cdm2, cdm3, idm3, idm4
      real :: temp
      real :: supcol, n0sfac, lamdas
      real :: diai      ! diameter of ice in m
      double precision :: lamc, lamco
      double precision :: lami, lamio
      logical :: has_qc, has_qi, has_qs
!..Minimum microphys values
      real, parameter :: R1 = 1.E-12
      real, parameter :: R2 = 1.E-6
      real, parameter :: pi = 3.1415926536
      real, parameter :: bm_r = 3.0
      real, parameter :: obmr = 1.0/bm_r
!      real, parameter :: cdm  = 2./3.
!-----------------------------------------------------------------------
      has_qc = .false.
      has_qi = .false.
      has_qs = .false.

      cdm2 = rgmma(2./(xmu_c+1.)+1.)
      cdm3 = rgmma(3./(xmu_c+1.)+1.)
      idm3 = rgmma(3.+xmu_i)
      idm4 = rgmma(4.+xmu_i)
      do k=kts,kte
        ! for cloud
        rqc(k) = max(R1, qc(k)*rho(k))
        rnc(k) = max(R2, nc(k)*rho(k))
        if (rqc(k).gt.R1 .and. rnc(k).gt.R2) has_qc = .true.
        ! for ice
        rqi(k) = max(R1, qi(k)*rho(k))
        rni(k) = max(R2, ni(k)*rho(k))
        if (rqi(k).gt.R1 .and. rni(k).gt.R2) has_qi = .true.
        ! for snow
        rqs(k) = max(R1, qs(k)*rho(k))
        if (rqs(k).gt.R1) has_qs = .true.
      enddo

      if (has_qc) then
        do k=kts,kte
          if (rqc(k).le.R1 .or. rnc(k).le.R2) CYCLE
!          lamc = 2.*cdm2*(pidnc*nc(k)/rqc(k))**obmr
          lamc = (pidnc*nc(k)/rqc(k))**(1./xbm_r)
          lamco =  lamc*2*cdm2/cdm3
          re_qc(k) =  max(2.51e-6,min(sngl(1.0d0/lamco),50.e-6))
        enddo
      endif

      if (has_qi) then
        do k=kts,kte
          if (rqi(k).le.R1 .or. rni(k).le.R2) CYCLE
           lami = (pidni*ni(k)/rqi(k))**(1./xbm_i) 
           lamio = lami*2*idm4/idm3
           re_qi(k) = max(10.01e-6,min(sngl(1.0d0/lamio),125.e-6))
        enddo
      endif

      if (has_qs) then
        do k=kts,kte
          if (rqs(k).le.R1) CYCLE
          supcol = t0c-t(k)
          n0sfac = max(min(exp(alpha*supcol),n0smax/n0s),1.)
!          lamdas = sqrt(sqrt(pidn0s*n0sfac/rqs(k))) 
          lamdas = exp(log((pidn0s*n0sfac/rqs(k)))*(1./(xbm_s+1))) 
          re_qs(k) = max(25.e-6,min(0.5*(1./lamdas),999.e-6))
        enddo
      endif

      end subroutine effectRad_kdm6
!-----------------------------------------------------------------------

END MODULE module_mp_kdm6
