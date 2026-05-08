!
!
!
!
MODULE module_cu_ksas
CONTAINS
!-------------------------------------------------------------------------------
   subroutine cu_ksas(dt,dx,p3di,p3d,pi3d,qc3d,qi3d,rho3d,itimestep,stepcu,    &
                     hbot,htop,cu_act_flag,                                    &
                     rthcuten,rqvcuten,rqccuten,rqicuten,                      &
                     rucuten,rvcuten,                                          &
                     qv3d,t3d,raincv,pratec,xland,dz8w,w,u3d,v3d,              &
                     hpbl,hfx,qfx,                                             &
                     hpbl_hold,znu,                                            &
                     mp_physics,dx_factor_nsas,                                &
                     p_qc,p_qi,p_first_scalar,                                 &
                     pgcon,                                                    &
                     cp,cliq,cpv,g,xlv,r_d,r_v,ep_1,ep_2,                      &
                     cice,xls,psat,f_qi,f_qc,                                  &
                     ids,ide, jds,jde, kds,kde,                                &
                     ims,ime, jms,jme, kms,kme,                                &
                     its,ite, jts,jte, kts,kte)
!-------------------------------------------------------------------------------
   implicit none
!-------------------------------------------------------------------------------
!-- dt          time step (s)
!-- dx          grid interval (m)
!-- p3di        3d pressure (pa) at interface level
!-- p3d         3d pressure (pa)
!-- pi3d        3d exner function (dimensionless)
!-- z           height above sea level (m)
!-- qc3d        cloud water mixing ratio (kg/kg)
!-- qi3d        cloud ice mixing ratio (kg/kg)
!-- qv3d        3d water vapor mixing ratio (kg/kg)
!-- t3d         temperature (k)
!-- raincv      cumulus scheme precipitation (mm)
!-- w           vertical velocity (m/s)
!-- dz8w        dz between full levels (m)
!-- u3d         3d u-velocity interpolated to theta points (m/s)
!-- v3d         3d v-velocity interpolated to theta points (m/s)
!-- ids         start index for i in domain 
!-- ide         end index for i in domain
!-- jds         start index for j in domain
!-- jde         end index for j in domain
!-- kds         start index for k in domain
!-- kde         end index for k in domain
!-- ims         start index for i in memory
!-- ime         end index for i in memory
!-- jms         start index for j in memory
!-- jme         end index for j in memory
!-- kms         start index for k in memory
!-- kme         end index for k in memory 
!-- its         start index for i in tile
!-- ite         end index for i in tile
!-- jts         start index for j in tile
!-- jte         end index for j in tile
!-- kts         start index for k in tile
!-- kte         end index for k in tile
!-------------------------------------------------------------------------------
   integer,  intent(in   )   ::       ids,ide, jds,jde, kds,kde,               &
                                      ims,ime, jms,jme, kms,kme,               &
                                      its,ite, jts,jte, kts,kte,               &
                                      itimestep, stepcu,                       &
                                      p_qc,p_qi,p_first_scalar
   real,     intent(in   )   ::      cp,cliq,cpv,g,xlv,r_d,r_v,ep_1,ep_2,      &
                                     cice,xls,psat
   real,     intent(in   )   ::      dt,dx
   real,     optional, intent(in ) :: pgcon
   real,     dimension( ims:ime, kms:kme, jms:jme ),optional                  ,&
             intent(inout)   ::                                       rthcuten,&
                                                                       rucuten,&
                                                                       rvcuten,&
                                                                      rqccuten,&
                                                                      rqicuten,&
                                                                      rqvcuten
   logical, optional ::                                              F_QC,F_QI
   real,     dimension( ims:ime, kms:kme, jms:jme )                           ,&
             intent(in   )   ::                                           qv3d,&
                                                                          qc3d,&
                                                                          qi3d,&
                                                                         rho3d,&
                                                                           p3d,&
                                                                          pi3d,&
                                                                           t3d
   real,     dimension( ims:ime, kms:kme, jms:jme )                           ,&
             intent(in   )   ::                                           p3di
   real,     dimension( ims:ime, kms:kme, jms:jme )                           ,&
             intent(in   )   ::                                           dz8w,&  
                                                                             w
   real,     dimension( ims:ime, jms:jme )                                    ,&
             intent(inout) ::                                           raincv,&
                                                                        pratec
   real,     dimension( ims:ime, jms:jme )                                    ,&
             intent(out) ::                                               hbot,&
                                                                          htop
!
   real,     dimension( ims:ime, jms:jme )                                    ,&
             intent(in   ) ::                                            xland
!
   real,     dimension( ims:ime, kms:kme, jms:jme )                           ,&
              intent(in   )   ::                                           u3d,&
                                                                           v3d
   logical,  dimension( ims:ime, jms:jme )                                    ,&
             intent(inout) ::                                      cu_act_flag
!
   real,     dimension( ims:ime, jms:jme )                                    ,&
              intent(in   )   ::                                          hpbl,&
                                                                     hpbl_hold,&
                                                                           hfx,&
                                                                           qfx
   real,     dimension( kms:kme )                                             ,&
              intent(in   )   ::                                           znu 
   integer,   intent(in   )   ::                                    mp_physics
   integer,   intent(in   )   ::                                dx_factor_nsas 
   integer :: ncloud
!
!local
!
   real,  dimension( its:ite, jts:jte )  ::                            raincv1,&
                                                                       pratec1

   real,   dimension( its:ite, kts:kte )  ::                               del,&
                                                                         prsll,&
                                                                           dot,&
                                                                            u1,&
                                                                            v1,&
                                                                            t1,&
                                                                           q1, &
                                                                           qc2,&
                                                                           qi2
   real,   dimension( its:ite, kts:kte+1 )  ::                           prsii,&
                                                                           zii
   real,   dimension( its:ite, kts:kte )  ::                               zll 
   real,   dimension( its:ite)  ::                                         rain
   real ::                                                          delt,rdelt
   integer, dimension (its:ite)  ::                                       kbot,&
                                                                          ktop,&
                                                                          icps
   real :: pgcon_use
   integer ::  i,j,k,kp, kbmax,kbm,kmax
! add
   integer ::  im,kx,kx1
!
! microphysics scheme --> ncloud 
!
   if (mp_physics .eq. 0) then
     ncloud = 0
   elseif ( mp_physics .eq. 1 .or. mp_physics .eq. 3 ) then
     ncloud = 1
   else
     ncloud = 2
   endif
!
   if(present(pgcon)) then
     pgcon_use = pgcon
   else
!    pgcon_use  = 0.7     ! Gregory et al. (1997, QJRMS)
     pgcon_use  = 0.55    ! Zhang & Wu (2003,JAS)
     ! 0.55 is a physically-based value used by GFS
     ! HWRF uses 0.2, for model tuning purposes
   endif
!
   do j = jts,jte
     do i = its,ite
       cu_act_flag(i,j)=.TRUE.
     enddo
   enddo
! add
   im=ite-its+1 
   kx=kte-kts+1 
   kx1=kx+1     

   delt=dt*stepcu
   rdelt=1./delt

   kbmax = kte
   kbm   = kte
   kmax  = kte
   do k = kts,kte
     if(znu(k).gt.0.45) kbmax = k + 1
     if(znu(k).gt.0.70) kbm   = k + 1
     if(znu(k).gt.0.05) kmax  = k + 1
   enddo
!
! outer most J_loop
!
   do j = jts,jte
     do k = kts,kte
       kp = k+1
       do i = its,ite
         dot(i,k) = -5.0e-4*g*rho3d(i,k,j)*(w(i,k,j)+w(i,kp,j))
         prsll(i,k)=p3d(i,k,j)  ! jhsim *0.001
         prsii(i,k)=p3di(i,k,j) ! jhsim*0.001
       enddo
     enddo
!
     do i = its,ite
       prsii(i,kte+1)=p3di(i,kte+1,j) ! jhsim*0.001
     enddo
!
     do i = its,ite
       zii(i,1)=0.0
     enddo     
!
     do k = kts,kte                                            
       do i = its,ite
         zii(i,k+1)=zii(i,k)+dz8w(i,k,j)
       enddo
     enddo
!
     do k = kts,kte                
       do i = its,ite                                                  
         zll(i,k)=0.5*(zii(i,k)+zii(i,k+1))
       enddo                                                         
     enddo
!
     do k = kts,kte
       do i = its,ite
         del(i,k)=prsll(i,k)*g/r_d*dz8w(i,k,j)/t3d(i,k,j)*0.001 !jhsim
         u1(i,k)=u3d(i,k,j)
         v1(i,k)=v3d(i,k,j)
         q1(i,k)=qv3d(i,k,j)
!        q1(i,k)=qv3d(i,k,j)/(1.+qv3d(i,k,j))
         t1(i,k)=t3d(i,k,j)
         qi2(i,k) = qi3d(i,k,j)
         qc2(i,k) = qc3d(i,k,j)
       enddo
     enddo
!
! NCEP SAS 
!
     call nsas2d(delt=delt,delx=dx,del=del(its,kts),                           &
              prsl=prsll(its,kts),prsi=prsii(its,kts),prslk=pi3d(ims,kms,j),   &
              zl=zll(its,kts), zi=zii(its,kts),                                & !add
              ncloud=ncloud,qc2=qc2(its,kts),qi2=qi2(its,kts),                 &
              q1=q1(its,kts),t1=t1(its,kts),rain=rain(its),                    &
              kbot=kbot(its),ktop=ktop(its),                                   &
              icps=icps(its),                                                  &
              lat=j,slimsk=xland(ims,j),dot=dot(its,kts),                      &
              u1=u1(its,kts), v1=v1(its,kts),                                  &
              cp_=cp,cliq_=cliq,cvap_=cpv,g_=g,hvap_=xlv,                      &
              rd_=r_d,rv_=r_v,fv_=ep_1,ep2=ep_2,                               &
              cice=cice,xls=xls,psat=psat,                                     &
              dx_factor_nsas=dx_factor_nsas,                                   &
              hpbl=hpbl(ims,j),hpbl_hold=hpbl_hold(ims,j),                     &
              kbmax=kbmax,kbm=kbm,kmax=kmax,                                   &
              lq=im, km=kx, km1=kx1,                                           & !add
              ids=ids,ide=ide, jds=jds,jde=jde, kds=kds,kde=kde,               &
              ims=ims,ime=ime, jms=jms,jme=jme, kms=kms,kme=kme,               &
              its=its,ite=ite, jts=jts,jte=jte, kts=kts,kte=kte   )
!
     do i = its,ite
       pratec1(i,j)=rain(i)*1000./(stepcu*dt)
       raincv1(i,j)=rain(i)*1000./(stepcu)
     enddo

     do i = its,ite
       raincv(i,j) = raincv1(i,j)
       pratec(i,j) = pratec1(i,j)
       hbot(i,j) = kbot(i)
       htop(i,j) = ktop(i)
     enddo
!
     IF(PRESENT(rthcuten).AND.PRESENT(rqvcuten)) THEN
       !jhsim do k = kts,kte
       do k = kts,kmax ! jhsim
         do i = its,ite
           rthcuten(i,k,j)=(t1(i,k)-t3d(i,k,j))/pi3d(i,k,j)*rdelt
           rqvcuten(i,k,j)=(q1(i,k)-qv3d(i,k,j))*rdelt
         enddo
       enddo
     ENDIF
!
     IF(PRESENT(rucuten).AND.PRESENT(rvcuten)) THEN
       !jhsim do k = kts,kte
       do k = kts,kmax ! jhsim
         do i = its,ite
           rucuten(i,k,j)=(u1(i,k)-u3d(i,k,j))*rdelt
           rvcuten(i,k,j)=(v1(i,k)-v3d(i,k,j))*rdelt
         enddo
       enddo
     ENDIF
!
     IF(PRESENT( rqicuten )) THEN
       IF ( F_QI ) THEN
         !jhsim do k = kts,kte
         do k = kts,kmax ! jhsim 
           do i = its,ite
             rqicuten(i,k,j)=(qi2(i,k)-qi3d(i,k,j))*rdelt
           enddo
         enddo
       ENDIF
     ENDIF
!
     IF(PRESENT( rqccuten )) THEN
       IF ( F_QC ) THEN
         !jhsim do k = kts,kte
         do k = kts,kmax ! jhsim
           do i = its,ite
             rqccuten(i,k,j)=(qc2(i,k)-qc3d(i,k,j))*rdelt
           enddo
         enddo
       ENDIF
     ENDIF
!
   enddo ! outer most J_loop
!
   return
   end subroutine cu_ksas
!
!-------------------------------------------------------------------------------
! NCEP SAS (Deep Convection Scheme)
!-------------------------------------------------------------------------------
   subroutine nsas2d(delt,delx,del,prsl,prsi,prslk,zl,zi,                      & !add
            ncloud,                                                            &
            qc2,qi2,                                                           &
            q1,t1,rain,kbot,ktop,                                              &
            icps,                                                              &
            lat,slimsk,dot,u1,v1,cp_,cliq_,cvap_,g_,hvap_,rd_,rv_,fv_,ep2,     &
            cice,xls,psat,                                                     &
            dx_factor_nsas,                                                    &
            hpbl,hpbl_hold,                                                    &
            kbmax,kbm,kmax,                                                    &
            lq,km,km1,                                                         & !add
            ids,ide, jds,jde, kds,kde,                                         &
            ims,ime, jms,jme, kms,kme,                                         &
            its,ite, jts,jte, kts,kte)
!-------------------------------------------------------------------------------
!
! subprogram:    phys_cps_sas      computes convective heating and moistening
!                                                      and momentum transport
!
! abstract: computes convective heating and moistening using a one
!   cloud type arakawa-schubert convection scheme originally developed
!   by georg grell. the scheme has been revised at ncep since initial 
!   implementation in 1993. it includes updraft and downdraft effects.
!   the closure is the cloud work function. both updraft and downdraft
!   are assumed to be saturated and the heating and moistening are
!   accomplished by the compensating environment. convective momentum transport
!   is taken into account. the name comes from "simplified arakawa-schubert
!   convection parameterization".
!
! developed by hua-lu pan, wan-shu wu, songyou hong, and jongil han
!   implemented into wrf by kyosun sunny lim and songyou hong
!   module with cpp-based options is available in grims 
!
! program history log:
!   92-03-01  hua-lu pan       operational development
!   96-03-01  song-you hong    revised closure, and trigger 
!   99-03-01  hua-lu pan       multiple clouds
!   06-03-01  young-hwa byun   closure based on moisture convergence (optional)
!   09-10-01  jung-eun kim     f90 format with standard physics modules
!   10-07-01  jong-il han      revised cloud model,trigger, as in gfs july 2010
!   10-12-01  kyosun sunny lim wrf compatible version
!   14-01-09  song-you hong    dx dependent trigger, closure, and mass flux
!   15-02-26  song-you hong    negative qv generation suppressed
!   15-06-01  jongil han       gfs sas
!   15-06-07  song-you hong    scale-aware cps
!   15-06-28  song-you hong    diurnal cycle with cldwrk in pbl
!   15-10-01  ji-young han     bug fix (dz to dz1)
!   16-01-01  ji-young han     enhanced entrainment at lower RH
!   16-06-01  ji-young han     moisture-based trigger threshold
!   16-09-01  ji-young han     bug fix & eliminate inconsistency
!   16-09-23  ji-young han     code clean-up
!   16-11-01  ji-young han     revised pgcon & bug fix in vshear
!   17-02-23  ji-young han     revised xlamb
!   18-03-01  ji-young han     kim sas
!   19-03-01  ji-yeon jang     revised triggering ftn for higher resolution<10km
!             yong-hee lee
!             young cheol kwon
!             eun-jeong lee    bug fix in c0 for overshooting layer
!             seung-bu park    bug fix in xmb trigger
!
! usage:    call phys_cps_sas(delt,delx,del,prsl,prsi,prslk,prsik,zl,          &
!                             q2,q1,t1,u1,v1,rcs,slimsk,dot,cldwrk,rain,       &
!                             jcap,ncloud,lat,kbot,ktop,icps,                  &
!                             ids,ide, jds,jde, kds,kde,                       &
!                             ims,ime, jms,jme, kms,kme,                       &
!                             its,ite, jts,jte, kts,kte)
!
!   delt     - real model integration time step
!   delx     - real model grid interval
!   del      - real (kms:kme) sigma layer thickness
!   prsl     - real (ims:ime,kms:kme) pressure values
!   prsi     - real (ims:ime,kms:kme) pressure values at interface level
!   prslk    - real (ims:ime,kms:kme) pressure values to the kappa
!   prsik    - real (ims:ime,kms:kme) pressure values to the kappa at interface lev.
!   zl       - real (ims:ime,kms:kme) height above sea level
!   zi       - real (ims:ime,kms:kme) height above sea level at interface level
!   rcs      - real
!   slimsk   - real (ims:ime) land(1),sea(0), ice(2) flag
!   dot      - real (ims:ime,kms:kme) vertical velocity
!   jcap     - integer wave number 
!   ncloud   - integer no_cloud(0),no_ice(1),cloud+ice(2) 
!   lat      - integer  current latitude index
!
! output argument list:
!   q2       - real (ims:ime,kms:kme) detrained hydrometeors in kg/kg
!            - in case of the  --> qc2(cloud), qi2(ice)
!   q1       - real (ims:ime,kms:kme) adjusted specific humidity in kg/kg
!   t1       - real (ims:ime,kms:kme) adjusted temperature in kelvin
!   u1       - real (ims:ime,kms:kme) adjusted zonal wind in m/s
!   v1       - real (ims:ime,kms:kme) adjusted meridional wind in m/s
!   cldwrk   - real (ims:ime) cloud work function
!   rain     - real (ims:ime) convective rain in meters
!   kbot     - integer (ims:ime) cloud bottom level
!   ktop     - integer (ims:ime) cloud top level
!   icps     - integer (ims:ime) bit flag indicating deep convection
!
! subprograms called:
!   fpvs     - function to compute saturation vapor pressure
!
! remarks: function fpvs is inlined by fpp.
!          nonstandard automatic arrays are used.
!
! references :
!   pan and wu    (1995, ncep office note)
!   hong and pan  (1998, mon wea rev)
!   park and hong (2007,jmsj)
!   byun and hong (2007, mon wea rev)
!   han and pan   (2011, wea. forecasting)
!   lim et al.    (2014, wea. forecasting)
!   han et al.    (2016, mon wea rev)
!   kwon and hong (2017, mon wea rev)
!   han and hong  (2018, wea. forecasting)
!
!-------------------------------------------------------------------------------
   implicit none
!-------------------------------------------------------------------------------
!
! model tunable parameters 
!
   real,parameter  ::  betal  = 0.05,   betas  = 0.05
   real,parameter  ::  c0     = 0.002,  c1     = 0.002
   real,parameter  ::  xlamdd = 1.0e-4, xlamde = 1.0e-4
   real,parameter  ::  clam   = 0.1,    cxlamu = 1.0e-3
   real,parameter  ::  aafac  = 0.1
   real,parameter  ::  dthk   = 25.
   real,parameter  ::  cinpcrmx = 240.,cinpcrmn = 120.
   real,parameter  ::  cinacrmx = -120.
   real,parameter  ::  bet1 = 1.875, cd1 = 0.506
   real,parameter  ::  f1   = 2.0,  gam1 = 0.5,  tfac = 1.0
   real,parameter  ::  dx1km = 1000., dx5km = 5000., dx250m = 250.
   real,parameter  ::  edtmaxl = 0.3, edtmaxs = 0.3
   real,parameter  ::  evfacts = 0.3, evfactl = 0.3
   real,parameter  ::  tf=233.16,tcr=273.16,tcrf=1.0/(tcr-tf)
!
!  passing variables
!
   real            ::  cp_,cliq_,cvap_,g_,hvap_,rd_,rv_,fv_,ep2
   real            ::  pi_,qmin_,t0c_,cice,xlv0,xls,psat
   integer         ::  dx_factor_nsas
   integer         ::  lat,                                                    &
                       ncloud,                                                 &
                       lq,km,km1,                                              & !add
                       ids,ide, jds,jde, kds,kde,                              &
                       ims,ime, jms,jme, kms,kme,                              &
                       its,ite, jts,jte, kts,kte
!
   real            ::  delt,rcs
   real            ::  del(its:ite,kts:kte),                                   &
                       prsl(its:ite,kts:kte),prslk(ims:ime,kms:kme),           &
                       prsi(its:ite,kts:kte+1),                                &
                       zl(its:ite,kts:kte),                                    &
                       q1(its:ite,kts:kte),t1(its:ite,kts:kte),                &
                       u1(its:ite,kts:kte),v1(its:ite,kts:kte),                &
                       qci(its:ite,kts:kte),qrs(its:ite,kts:kte),              &
                       dot(its:ite,kts:kte)
   real            ::  qi2(its:ite,kts:kte)
   real            ::  qc2(its:ite,kts:kte)
!
   real            ::  rain(its:ite)
   real            ::  hpbl(ims:ime),hpbl_hold(ims:ime)
   integer         ::  kbot(its:ite),ktop(its:ite),icps(its:ite)
   real            ::  slimsk(ims:ime)
!
!  local variables and arrays
!
   integer         ::  i,k,kmax,kbmax,kbm,jmn,indx,     kts1,kte1,kmax1,kk
   real            ::  p(its:ite,kts:kte),pdot(its:ite),acrtfct(its:ite)
   real            ::  pden(its:ite)
   real            ::  zi(its:ite,kts:kte+1)
   real            ::  uo(its:ite,kts:kte),vo(its:ite,kts:kte)
   real            ::  to(its:ite,kts:kte),qo(its:ite,kts:kte)
   real            ::  hcko(its:ite,kts:kte)
   real            ::  qcko(its:ite,kts:kte),eta(its:ite,kts:kte)
   real            ::  etad(its:ite,kts:kte)
   real            ::  qrcdo(its:ite,kts:kte)
   real            ::  pwo(its:ite,kts:kte),pwdo(its:ite,kts:kte)
   real            ::  c0t(its:ite,kts:kte)
   real            ::  c1t(its:ite,kts:kte)
   real            ::  bb1, bb2, wucb
   real            ::  cinpcr
   real            ::  cinacr
!
! for updraft velocity calculation
!
   real            ::  po1(its:ite,kts:kte),wu2(its:ite,kts:kte),              &
                       buo(its:ite,kts:kte),drag(its:ite,kts:kte)
   real            ::  wbar(its:ite),wc(its:ite),clear(its:ite)
!
   real            ::  sigma, sigma_con
   real            ::  mbdt
   real            ::  dtconv(its:ite)
   real            ::  deltv(its:ite),acrt(its:ite)
   real            ::  apbl(its:ite),dtpbl(its:ite)
   real            ::  qeso(its:ite,kts:kte)
   real            ::  tvo(its:ite,kts:kte),dbyo(its:ite,kts:kte)
   real            ::  heo(its:ite,kts:kte),heso(its:ite,kts:kte),kb_heo(its:ite) ! add
   real            ::  qrcd(its:ite,kts:kte)
   real            ::  dellah(its:ite,kts:kte),dellaq(its:ite,kts:kte)
!
   integer         ::  kb(its:ite),kbcon(its:ite)
   integer         ::  kbcon1(its:ite)
   real            ::  hmax(its:ite),delq(its:ite)
   real            ::  hkbo(its:ite),qkbo(its:ite)
   integer         ::  lmin(its:ite),jmin(its:ite)
   integer         ::  ktcon(its:ite)
   integer         ::  ktcon1(its:ite)
   integer         ::  n_kb(its:ite), n_kbcon1(its:ite), n_ktcon(its:ite) ! add
   integer         ::  kbdtr(its:ite)
   real            ::  hmin(its:ite),pwavo(its:ite)
   real            ::  aa1(its:ite),vshear(its:ite)
   real            ::  qevap(its:ite)
   real            ::  edt(its:ite)
   real            ::  edt_s(its:ite)
   real            ::  edto(its:ite),pwevo(its:ite)
   real            ::  qcond(its:ite)
   real            ::  hcdo(its:ite,kts:kte)
   real            ::  qcdo(its:ite,kts:kte)
   real            ::  xhkb(its:ite),xqkb(its:ite)
   real            ::  xpwav(its:ite),xpwev(its:ite),xhcd(its:ite,kts:kte)
   real            ::  xaa0(its:ite),f(its:ite),xk(its:ite)
   real            ::  xmb(its:ite)
   real            ::  edtx(its:ite),xqcd(its:ite,kts:kte)
   real            ::  hsbar(its:ite),xmbmax(its:ite)
   real            ::  xlamb(its:ite,kts:kte),xlamd(its:ite)
   real            ::  cina(its:ite)
   real            ::  delhbar(its:ite),delqbar(its:ite),deltbar(its:ite)
   real            ::  qcirs(its:ite,kts:kte)
   real            ::  dellal(its:ite,kts:kte)
   real            ::  rntot(its:ite),delqev(its:ite),delq2(its:ite) 
!
   real            ::  fent1(its:ite,kts:kte),fent2(its:ite,kts:kte)
   real            ::  frh(its:ite,kts:kte)
   real            ::  xlamud(its:ite),sumx(its:ite)
   real            ::  frh_sum(its:ite),cinpcri(its:ite)
   real            ::  aa2(its:ite)
   real            ::  ucko(its:ite,kts:kte),vcko(its:ite,kts:kte)
   real            ::  ucdo(its:ite,kts:kte),vcdo(its:ite,kts:kte)
   real            ::  dellau(its:ite,kts:kte),dellav(its:ite,kts:kte)
   real            ::  delubar(its:ite),delvbar(its:ite)
   real            ::  qlko_ktcon(its:ite)
!
   real            ::  alpha,beta,                                             &
                       dt2,dtmin,dtmax,                                        &
                       el2orc,eps,fact1,fact2,                                 &
                       tem,tem1
   real            ::  dz,dp,es,pprime,qs,                                     &
                       dqsdp,desdt,dqsdt,gamma,                                &
                            c0fac,alpha1,beta1,ccn_f,                          &
                       dt,dq,po,     delx,                                     &
                       factor,onemf,dz1,qrch,etah,qlk,qc,rfact,shear,          &
                       e1,dh,                 edtmax,dhh,dg,aup,adw,           &
                       dv1,dv2,dv3,dv1q,dv2q,dv3q,                             &
                       dv1u,dv2u,dv3u,dv1v,dv2v,dv3v,                          &
                       dellat,xdby,xqrch,    xpw,xpwd,                         &
                       qrsk(its:ite,kts:kte),evef,ptem,ptem1
!
   logical         ::  totflg, cnvflg(its:ite),flg(its:ite)
   logical         ::  n_cnvflg(its:ite) ! add
   real            ::  pgcon(its:ite,kts:kte)
!
!-----------------------------------------------------------------------
!
! define miscellaneous values
!
   pi_   = 3.14159
   qmin_ = 1.0e-30
   t0c_ = 273.15
   xlv0 = hvap_
   rcs  = 1.
   el2orc = hvap_*hvap_/(rv_*cp_)
   eps    = rd_/rv_
   fact1  = (cvap_-cliq_)/rv_
   fact2  = hvap_/rv_-fact1*t0c_
   kts1 = kts + 1
   kte1 = kte - 1
   dt2    = delt
   dtmin  = max(dt2,600.)
   dtmax  = max(dt2,10800.)
   mbdt   = dt2
   sigma_con = tan(0.4*pi_)/(dx5km-dx1km)                     ! 7.7 e-4 m-1
   sigma  = (1.-1./pi_*(atan(sigma_con*(delx-dx5km))+pi_/2.)) ! 1(1km),0.1(10km)
!
   if (delx.lt.dx5km) then
     sigma = min(sigma - 0.01684 * delx/1000. + 0.0842, 1.0)
   endif
!
   cinpcr = (cinpcrmn + 0.5*(cinpcrmx-cinpcrmn)) * (1.-sigma)
!
!  initialize arrays
!
   do i = its,ite
     rain(i)    = 0.0
     kbot(i)    = kte+1
     ktop(i)    = 0
     icps(i)    = 0
     cnvflg(i)  = .false. ! rev
     kb_heo(i)  = 0.0     ! add
     n_kbcon1(i)= 0       ! add
     n_ktcon(i) = 0       ! add
     n_kb(i)    = 0       ! add
     dtconv(i)  = 3600.
     pdot(i)    = 0.0
     edto(i)    = 0.0
     edtx(i)    = 0.0
     xmbmax(i)  = 0.3
     aa2(i)     = 0.0
     qlko_ktcon(i) = 0.0
     lmin(i)    = 1
     jmin(i)    = 1
     edt(i)     = 0.0
     cina(i)    = 0.0
     frh_sum(i) = 0.0
     cinpcri(i) = 0.0
     apbl(i)    = 0.0
     dtpbl(i)   = 0.0
     do k = kts,kte
       pgcon(i,k) = 0.5
     enddo
   enddo
!
! Define top layer for search of the downdraft originating layer
! and the maximum thetae for updraft
!
   kmax = min(kmax,kte)
   kmax1 = kmax - 1
   kbm = min(kbm,kte)
!
! convert surface pressure to mb from cb
!
   do k = kts,kte
     do i = its,ite
       c0t(i,k)  = c0
       c1t(i,k)  = c1 * sigma
       qcirs(i,k)= 0.0
       qci(i,k)  = 0.0
       qrs(i,k)  = 0.0
       qrsk(i,k) = 0.0
       wu2(i,k)  = 0.0
       buo(i,k)  = 0.0
       drag(i,k) = 0.0
       pwo(i,k)  = 0.0
       pwdo(i,k) = 0.0
       dellal(i,k) = 0.0
       hcko(i,k) = 0.0
       qcko(i,k) = 0.0
       hcdo(i,k) = 0.0
       qcdo(i,k) = 0.0
     enddo
   enddo
!
   do k = kts,kmax
     do i = its,ite
!       p(i,k) = prsl(i,k) * 10. revised
       p(i,k) = prsl(i,k) * 0.01
       to(i,k) = t1(i,k)
       qo(i,k) = q1(i,k)
       dbyo(i,k) = 0.0
       fent1(i,k) = 1.0
       fent2(i,k) = 1.0
       frh(i,k) = 0.0
       ucko(i,k) = 0.0
       vcko(i,k) = 0.0
       ucdo(i,k) = 0.0
       vcdo(i,k) = 0.0
       uo(i,k) = u1(i,k) * rcs
       vo(i,k) = v1(i,k) * rcs
     enddo
   enddo
!
! column variables
!
!  p is pressure of the layer (mb)
!  t is temperature at t-dt (k)..tn
!  q is mixing ratio at t-dt (kg/kg)..qn
!  to is temperature at t+dt (k)... this is after advection and turbulan
!  qo is mixing ratio at t+dt (kg/kg)..q1
!
! add 
  call trigger_ntdk &
  &     (its=its, ite=ite, kts=kts, kte=kmax, & ! jhsim
  &      rpten=t1, rpren=q1, rpgeo=g_*zl, rpaph=prsi, rpgeoh=g_*zi,&
  &      rpap=prsl,&
  &      cpd=cp_, rd=rd_, rv=rv_, alv=hvap_, als=xls,&
  &      g=g_, kb_heo=kb_heo,&
  &      cubot=n_kbcon1, cutop=n_ktcon, kdpl=n_kb, ldcum=cnvflg)

   do k = kts,kmax
     do i = its,ite
       qeso(i,k)=0.01*fpvs(to(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
       qeso(i,k) = eps * qeso(i,k) / (p(i,k) + (eps-1.) * qeso(i,k))
       qeso(i,k) = max(qeso(i,k),qmin_)
       qo(i,k)   = max(qo(i,k), 1.e-10 )
!      tvo(i,k)  = to(i,k) + fv_ * to(i,k) * max(qo(i,k),qmin_)
     enddo
   enddo
!
! compute moist static energy
!
   do k = kts,kmax
     do i = its,ite
       heo(i,k)  = g_ * zl(i,k) + cp_* to(i,k) + hvap_ * qo(i,k)
       heso(i,k) = g_ * zl(i,k) + cp_* to(i,k) + hvap_ * qeso(i,k)
     enddo
   enddo
!
! Determine level with largest moist static energy
! This is the level where updraft starts
!
   do i = its,ite
     kb(i) = 1
     if (cnvflg(i)) then
       kb(i) = n_kb(i)
     endif
   enddo

! revised-blocked
!   do i = its,ite
!     if (qo(i,kb(i)).lt.qmin_) cnvflg(i) = .false.
!   enddo
   do k = kts,kmax1
     do i = its,ite
       if(cnvflg(i)) then
         dz = .5 * (zl(i,k+1) - zl(i,k))
         dp = .5 * (p(i,k+1) - p(i,k))
         es = 0.01*fpvs(to(i,k+1),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         pprime = p(i,k+1) + (eps-1.) * es
         qs = eps * es / pprime
         dqsdp = - qs / pprime
         desdt = es * (fact1 / to(i,k+1) + fact2 / (to(i,k+1)**2))
         dqsdt = qs * p(i,k+1) * desdt / (es * pprime)
         gamma = el2orc * qeso(i,k+1) / (to(i,k+1)**2)
         dt = (g_ * dz + hvap_ * dqsdp * dp) / (cp_ * (1. + gamma))
         dq = dqsdt * dt + dqsdp * dp
         to(i,k) = to(i,k+1) + dt
         qo(i,k) = qo(i,k+1) + dq
         po = .5 * (p(i,k) + p(i,k+1))
         qeso(i,k)=0.01*fpvs(to(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k) / (po + (eps-1.) * qeso(i,k))
         qeso(i,k) = max(qeso(i,k),qmin_)
         qo(i,k)   = max(qo(i,k), 1.e-10)
         frh(i,k)  = 1. - min(qo(i,k)/qeso(i,k), 1.)
         heo(i,k)  = .5 * g_ * (zl(i,k) + zl(i,k+1)) +                         &
                cp_ * to(i,k) + hvap_ * qo(i,k)
         heso(i,k) = .5 * g_ * (zl(i,k) + zl(i,k+1)) +                         &
                cp_ * to(i,k) + hvap_ * qeso(i,k)
         uo(i,k)   = .5 * (uo(i,k) + uo(i,k+1))
         vo(i,k)   = .5 * (vo(i,k) + vo(i,k+1))
       endif
     enddo
   enddo
!
! look for convective cloud base as the level of free convection
!
   do i = its,ite
     if(cnvflg(i)) then
       indx = kb(i)
       hkbo(i) = kb_heo(i)
       qkbo(i) = qo(i,indx)
     endif
   enddo
!
   do i = its,ite
     flg(i) = cnvflg(i)
     kbcon(i) = kmax
   enddo
!
   do k = kts,kbmax
     do i = its,ite
       if(flg(i).and.k.gt.kb(i)) then
         hsbar(i) = heso(i,k)
         if(hkbo(i).gt.hsbar(i)) then
           flg(i) = .false.
           kbcon(i) = k
         endif
       endif
     enddo
   enddo
!
   do i = its,ite
     if(kbcon(i).eq.kmax) cnvflg(i) = .false.
   enddo
!
   do k = kts1,kte
     do i = its,ite
       zi(i,k) = 0.5*(zl(i,k-1)+zl(i,k))
     enddo
   enddo
!
   do k = kts,kte1
     do i = its,ite
       xlamb(i,k) = clam / zi(i,k+1) 
     enddo
   enddo
!
!  assume that updraft entrainment rate above cloud base is
!  same as that at cloud base
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.gt.kbcon(i))) then
         xlamb(i,k) = xlamb(i,kbcon(i))
       endif
     enddo
   enddo
!
!  assume the detrainment rate for the updrafts to be same as
!  the entrainment rate at cloud base
!
   do i = its,ite
     if(cnvflg(i)) then
       xlamud(i) = xlamb(i,kbcon(i))
     endif
   enddo
!
!  functions rapidly decreasing with height, mimicking a cloud ensemble
!    (Bechtold et al., 2008)
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.gt.kbcon(i))) then
         tem = qeso(i,k)/qeso(i,kbcon(i))
         fent1(i,k) = tem**2
         fent2(i,k) = tem**3
       endif
     enddo
   enddo
!
!  final entrainment rate as the sum of turbulent part and organized entrainment
!    depending on the environmental relative humidity
!    (Bechtold et al., 2008)
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.ge.kbcon(i))) then
          tem = cxlamu * frh(i,k) * fent2(i,k)
          xlamb(i,k) = xlamb(i,k)*fent1(i,k) + tem
       endif
     enddo
   enddo
!
! determine updraft mass flux
!
   do k = kts,kte
     do i = its,ite
      if(cnvflg(i)) then
         eta(i,k) = 1.
       endif
     enddo
   enddo
!
   do k = kbmax,kts1,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.kbcon(i).and.k.ge.kb(i)) then
         dz = zi(i,k+2) - zi(i,k+1)
         ptem     = 0.5*(xlamb(i,k)+xlamb(i,k+1))-xlamud(i)
         eta(i,k) = eta(i,k+1) / (1. + ptem * dz)
       endif
     enddo
   enddo
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.gt.kbcon(i)) then
         dz  = zi(i,k+1) - zi(i,k)
         ptem     = 0.5*(xlamb(i,k)+xlamb(i,k-1))-xlamud(i)
         eta(i,k) = eta(i,k-1) * (1 + ptem * dz)
       endif
     enddo
   enddo
   do i = its,ite
     if(cnvflg(i)) then
       dz = zi(i,3) - zi(i,2)
       ptem     = 0.5*(xlamb(i,1)+xlamb(i,2))-xlamud(i)
       eta(i,1) = eta(i,2) / (1. + ptem * dz)
     endif
   enddo
!
! work up updraft cloud properties
!
   do i = its,ite
     if(cnvflg(i)) then
       indx = kb(i)
       hcko(i,indx) = hkbo(i)
       qcko(i,indx) = qkbo(i)
       ucko(i,indx) = uo(i,indx)
       vcko(i,indx) = vo(i,indx)
       pwavo(i) = 0.
     endif
   enddo
!
! cloud property below cloud base is modified by the entrainment proces
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.gt.kb(i)) then
         dz   = zi(i,k+1) - zi(i,k)
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz
         tem1 = 0.5 * xlamud(i) * dz
         factor = 1. + tem - tem1
         hcko(i,k) = ((1.-tem1)*hcko(i,k-1)+tem*0.5*                           &
                     (heo(i,k)+heo(i,k-1)))/factor
         dbyo(i,k) = hcko(i,k) - heso(i,k)
       endif
     enddo
   enddo
!
!   taking account into convection inhibition due to existence of
!    dry layers below cloud base
!
   do i = its,ite
     kbcon1(i) = kmax
     if (cnvflg(i)) then
       kbcon1(i) = n_kbcon1(i)
       if(kbcon1(i).lt.kbcon(i)) then
         kbcon1(i) = kbcon(i)
       endif
     endif
   enddo

   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return

! calculate convective inhibition
!
   do k = kts1,kmax1
     do i = its,ite
       if (cnvflg(i)) then
         if (k.gt.kb(i).and.k.lt.kbcon1(i)) then
           dz1 = (zi(i,k+1) - zi(i,k))
           gamma = el2orc * qeso(i,k) / (to(i,k)**2)
           rfact =  1. + fv_ * cp_ * gamma * to(i,k) / hvap_
           cina(i) = cina(i) + dz1 * (g_ / (cp_ * to(i,k)))                    &
                   * dbyo(i,k) / (1. + gamma) * rfact
           cina(i) = cina(i) + dz1 * g_ * fv_ * max(0.,(qeso(i,k) - qo(i,k)))
         endif
       endif
     enddo
   enddo
!

   do i = its,ite
     ktcon(i) = 1
     if (cnvflg(i)) then
       ktcon(i) = n_ktcon(i)
     endif
   enddo
!
   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return
!
!  search for downdraft originating level above theta-e minimum
!
   do i = its,ite 
     if(cnvflg(i)) then
       hmin(i) = heo(i,kbcon1(i))
       lmin(i) = kbmax
       jmin(i) = kbmax
    endif
   enddo
!
   do k = kts1,kbmax 
     do i = its,ite 
       if(cnvflg(i).and.k.gt.kbcon1(i).and.heo(i,k).lt.hmin(i)) then
         lmin(i) = k + 1
         hmin(i) = heo(i,k)
       endif
     enddo
   enddo
!
! make sure that jmin is within the cloud
!
   do i = its,ite
     if(cnvflg(i)) then
       jmin(i) = min(lmin(i),ktcon(i)-1)
       jmin(i) = max(jmin(i),kbcon1(i)+1)
       if(jmin(i).ge.ktcon(i)) cnvflg(i) = .false.
       if(jmin(i).le.kbcon(i)) cnvflg(i) = .false.
     endif
   enddo
!
!  specify upper limit of mass flux at cloud base
!
   do i = its,ite
     if(cnvflg(i)) then
       k = kbcon(i)
       dp = 1000. * del(i,k)
       xmbmax(i) = dp / (g_ * dt2)
     endif
   enddo
!
! compute cloud moisture property and precipitation
!
   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i).and.k.gt.kb(i)) then
         alpha1 = min((-0.7*log(100.)+24.)*0.0001,c0)
         beta1 = 0.07
!
         if (to(i,k).gt.t0c_) then
           c0fac = alpha1
         else
           c0fac = alpha1*exp(beta1*(to(i,k)-t0c_))
         endif
!
         c0fac = max(0.0,c0fac)
         c0t(i,k) = c0fac
       endif
!
       if(cnvflg(i).and.k.gt.kb(i).and.k.lt.ktcon(i)) then
         dz1 = (zi(i,k+1) - zi(i,k))
         gamma = el2orc * qeso(i,k) / (to(i,k)**2)
         qrch = qeso(i,k)                                                      &
              + gamma * dbyo(i,k) / (hvap_ * (1. + gamma))
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz1
         tem1 = 0.5 * xlamud(i) * dz1
         factor = 1. + tem - tem1
         qcko(i,k) = ((1.-tem1)*qcko(i,k-1)+tem*0.5*                           &
                    (qo(i,k)+qo(i,k-1)))/factor
         qcirs(i,k) = eta(i,k) * qcko(i,k) - eta(i,k) * qrch
!
! check if there is excess moisture to release latent heat
!
         if(qcirs(i,k).gt.0. .and. k.ge.kbcon(i)) then
           etah = .5 * (eta(i,k) + eta(i,k-1))
           if(ncloud.gt.0..and.k.gt.jmin(i)) then
             dp = 1000. * del(i,k)
             ptem = c0t(i,k) + c1t(i,k)
             qlk = qcirs(i,k) / (eta(i,k) + etah * ptem * dz1)
             dellal(i,k) = etah * c1t(i,k) * dz1 * qlk * g_ / dp
           else
             qlk = qcirs(i,k) / (eta(i,k) + etah * c0t(i,k) * dz1)
           endif
           pwo(i,k) = etah * c0t(i,k) * dz1 * qlk
           qc = qlk + qrch
           qcko(i,k) = qc
           pwavo(i) = pwavo(i) + pwo(i,k)
           buo(i,k) = buo(i,k) - g_ * qlk
!
! compute buoyancy and drag for updraft velocity
!
           if (k.ge.kbcon(i)) then
             rfact = 1. + fv_ * cp_ * gamma                                    &
                     * to(i,k) / hvap_
             buo(i,k) = buo(i,k) + (g_ / (cp_ * to(i,k)))                      &
                      * dbyo(i,k) / (1. + gamma)                               &
                      * rfact
             buo(i,k) = buo(i,k) + g_ * fv_ *                                  &
                        max(0.,(qeso(i,k) - qo(i,k)))
             drag(i,k) = max(xlamb(i,k),xlamud(i))
           endif
         endif
       endif
     enddo
   enddo
!
! calculate cloud work function at t+dt
!
   do i = its,ite
     if (cnvflg(i)) then
       aa1(i) = 0.
     endif
   enddo
!
   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i)) then
         if (k.ge.kbcon(i) .and. k.lt.ktcon(i)) then
           dz1 = zl(i,k+1) - zl(i,k)
           aa1(i) = aa1(i) + buo(i,k) * dz1
         endif
       endif
     enddo
   enddo
!
   do i = its,ite
     if(cnvflg(i).and.aa1(i).le.0.) cnvflg(i) = .false.
   enddo
!
   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return
!
!    estimate the convective overshooting as the level
!    where the [aafac * cloud work function] becomes zero,
!    which is the final cloud top
!
   do i = its,ite
     if (cnvflg(i)) then
       aa2(i) = aafac * aa1(i)
     endif
   enddo
!
   do i = its,ite
     flg(i) = cnvflg(i)
     ktcon1(i) = kmax1
   enddo
!
   do k = kts1,kmax
     do i = its, ite
       if (flg(i)) then
         if(k.ge.ktcon(i).and.k.lt.kmax) then
           dz1 = zl(i,k+1) - zl(i,k)
           gamma = el2orc * qeso(i,k) / (to(i,k)**2)
           rfact =  1. + fv_ * cp_ * gamma* to(i,k) / hvap_
           aa2(i) = aa2(i) +dz1 * (g_ / (cp_ * to(i,k)))                       &
                       * dbyo(i,k) / (1. + gamma)* rfact
           if(aa2(i).lt.0.) then
             ktcon1(i) = k
             flg(i) = .false.
           endif
         endif
       endif
     enddo
   enddo
!
!  compute cloud moisture property, detraining cloud water
!  and precipitation in overshooting layers
!
   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i)) then
         if(k.ge.ktcon(i).and.k.lt.ktcon1(i)) then
           dz = (zi(i,k+1) - zi(i,k))
           gamma = el2orc * qeso(i,k) / (to(i,k)**2)
           qrch = qeso(i,k)+ gamma * dbyo(i,k) / (hvap_ * (1. + gamma))
           tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz
           tem1 = 0.5 * xlamud(i) * dz
           factor = 1. + tem - tem1
           qcko(i,k) = ((1.-tem1)*qcko(i,k-1)+tem*0.5*                         &
                      (qo(i,k)+qo(i,k-1)))/factor
           qcirs(i,k) = eta(i,k) * qcko(i,k) - eta(i,k) * qrch
!
!  check if there is excess moisture to release latent heat
!
           if(qcirs(i,k).gt.0.) then
             etah = .5 * (eta(i,k) + eta(i,k-1))
             if(ncloud.gt.0.) then
               dp = 1000. * del(i,k)
               qlk = qcirs(i,k) / (eta(i,k) + etah * (c0t(i,k) + c1t(i,k)) * dz)
               dellal(i,k) = etah * c1t(i,k) * dz * qlk * g_ / dp
             else
               qlk = qcirs(i,k) / (eta(i,k) + etah * c0t(i,k) * dz)
             endif
             pwo(i,k) = etah * c0t(i,k) * dz * qlk
             qc = qlk + qrch
             qcko(i,k) = qc
             pwavo(i) = pwavo(i) + pwo(i,k)
           endif
         endif
       endif
     enddo
   enddo
!
! compute updraft velocity square(wu2)
!
   bb1 = 2. * (1.+bet1*cd1)
   bb2 = 2. / (f1*(1.+gam1))
!
!  bb1 = 12.0
!  bb2 = 0.67
!
   do i = its,ite
     if (cnvflg(i)) then
       k = kbcon1(i)
       po = .5 * (p(i,k) + p(i,k+1))
       tem = po / (rd_ * to(i,k))
       wucb = -10.*dot(i,k) / (tem * g_)
       if (wucb.gt.0.) then
         wu2(i,k) = wucb * wucb
       else
         wu2(i,k) = 0.
       endif
     endif
   enddo
!
   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i)) then
         if (k.gt.kbcon1(i) .and. k.lt.ktcon(i)) then
           dz   = zi(i,k+1) - zi(i,k)
           tem  = 0.25 * bb1 * (drag(i,k)+drag(i,k-1)) * dz
           tem1 = 0.5 * bb2 * (buo(i,k)+buo(i,k-1)) * dz
           ptem = (1. - tem) * wu2(i,k-1)
           ptem1 = 1. + tem
           wu2(i,k) = (ptem + tem1) / ptem1
           wu2(i,k) = max(wu2(i,k), 0.)
         endif
       endif
     enddo
   enddo
!
! compute mean updraft velocity and mean grid-scale vertical velocity
!
   wc = 0. ; wbar = 0. ; sumx = 0.
!
   ptem = -0.5 * rd_ / g_
   do k = kts1,kmax
     do i = its,ite
       po1(i,k) = .5 * (p(i,k) + p(i,k+1))
     enddo
   enddo
!
   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i)) then
         if (k.gt.kbcon1(i) .and. k.lt.ktcon(i)) then
           dz = zi(i,k+1) - zi(i,k)
           tem = 0.5 * (sqrt(wu2(i,k)) + sqrt(wu2(i,k-1)))
           wc(i) = wc(i) + tem * dz
           tem  = 10. * dot(i,k)   * to(i,k)   / po1(i,k)
           tem1 = 10. * dot(i,k-1) * to(i,k-1) / po1(i,k-1)
           wbar(i) = wbar(i) + ptem * (tem + tem1) * dz
           sumx(i) = sumx(i) + dz
         endif
       endif
     enddo
   enddo
!
   do i = its,ite
     if (cnvflg(i)) then
       if (sumx(i) == 0.) then
         cnvflg(i) = .false.
       else
         wc(i) = wc(i) / sumx(i)
         wbar(i) = wbar(i) / sumx(i)
       endif
       if (wc(i).lt.1.e-4) cnvflg(i) = .false.
     endif
   enddo
!
! compute mean cloud core fraction
! assume mean cloud core fraction to be the ratio of
! mean grid-scale vertical velocity (wbar) and mean updraft velocity
!
   do i = its,ite
     if (cnvflg(i)) then
       tem = wbar(i) / wc(i)
       tem = max(tem, 0.)
       clear(i) = 1. - tem
       clear(i) = max(min(clear(i), 1.0), 0.)
       if (wbar(i).gt.0. .and. wbar(i).gt.wc(i)) cnvflg(i) = .false.
     endif
   enddo
!
! exchange ktcon with ktcon1
!
   do i = its,ite
     if(cnvflg(i)) then
       kk = ktcon(i)
       ktcon(i) = ktcon1(i)
       ktcon1(i) = kk
     endif
   enddo
!
   do i = its,ite
     if (ktcon(i).le.kb(i)) cnvflg(i) = .false.
   enddo
!
   do k = kts,kte
     do i = its,ite
       if (cnvflg(i)) then
         if (k.le.ktcon(i)) then
           pgcon(i,k) = 0.5+0.5*exp(3.*(zl(i,k)-zl(i,ktcon(i)))/zl(i,ktcon(i)))
         else
           pgcon(i,k) = 1.0
         endif
       endif
       pgcon(i,k) = min(pgcon(i,k), 1.0)
       pgcon(i,k) = max(pgcon(i,k), 0.5)
     enddo
   enddo
!
   do k = kts1,kmax1
     do i = its,ite
       if (cnvflg(i) .and. k.gt.kb(i)) then
         dz   = zi(i,k+1) - zi(i,k)
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz
         tem1 = 0.5 * xlamud(i) * dz
         factor = 1. + tem - tem1
         ptem  = 0.5 * tem + pgcon(i,k)
         ptem1 = 0.5 * tem - pgcon(i,k)
         ucko(i,k) = ((1.-tem1)*ucko(i,k-1)+ptem*uo(i,k)                       &
                     +ptem1*uo(i,k-1))/factor
         vcko(i,k) = ((1.-tem1)*vcko(i,k-1)+ptem*vo(i,k)                       &
                     +ptem1*vo(i,k-1))/factor
       endif
     enddo
   enddo
!
! this section is ready for cloud water
!
   if (ncloud.gt.0) then
!
!  compute liquid and vapor separation at cloud top
! 
     do i = its,ite
       if(cnvflg(i)) then
         k = ktcon(i)-1
         gamma = el2orc * qeso(i,k) / (to(i,k)**2)
         qrch = qeso(i,k)                                                      &
                + gamma * dbyo(i,k) / (hvap_ * (1. + gamma))
         dq = qcko(i,k) - qrch
!
!  check if there is excess moisture to release latent heat
!
         if(dq.gt.0.) then
           qlko_ktcon(i) = dq * sigma
           qcko(i,k) = qrch + dq * (1.-sigma)
         endif
       endif
     enddo
   endif
!
! ..... downdraft calculations .....
!
! determine downdraft strength in terms of wind shear
!
   do i = its,ite
     if(cnvflg(i)) then
       vshear(i) = 0.
     endif
   enddo
!
   do k = kts1,kmax
     do i = its,ite
       if(k.gt.kb(i).and.k.le.ktcon(i).and.cnvflg(i)) then
         shear= sqrt((uo(i,k)-uo(i,k-1)) ** 2                                  &
                   + (vo(i,k)-vo(i,k-1)) ** 2)
         vshear(i) = vshear(i) + shear
       endif
     enddo
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then
       vshear(i) = 1.e3 * vshear(i) / (zi(i,ktcon(i)+1)-zi(i,kb(i)+1))
       e1 = 1.591-.639*vshear(i)                                               &
           +.0953*(vshear(i)**2)-.00496*(vshear(i)**3)
       edt(i)  = 1.-e1
!
       ccn_f = 1.0
       edt_s(i) = edt(i)
       edt_s(i) = min(edt_s(i),.9)
       edt_s(i) = max(edt_s(i),.0)
       edt(i)  = min(edt(i),.9)
       edt(i)  = max(edt(i),.0)
       edt(i)  = edt(i) * ccn_f
       edto(i) = edt(i)
       edtx(i) = edt(i)
     endif
   enddo
!
! determine detrainment rate between 1 and kbdtr
!
   do i = its,ite
     if(cnvflg(i)) then
       sumx(i) = 0.
     endif
   enddo
!
   do k = kts,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.ge.1.and.k.lt.kbcon(i)) then
         dz = zi(i,k+2) - zi(i,k+1)
         sumx(i) = sumx(i) + dz
       endif
     enddo
   enddo
!
   do i = its,ite
     beta = betas
     if(slimsk(i).eq.1.) beta = betal
     if(cnvflg(i)) then
       kbdtr(i) = kbcon(i)
       kbdtr(i) = max(kbdtr(i),1)
       dz =(sumx(i)+zi(i,2))/float(kbcon(i))
       tem = 1./float(kbcon(i))
       xlamd(i) = (1.-beta**tem)/dz
     endif
   enddo
!
! determine downdraft mass flux
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i)) then
         etad(i,k) = 1.
       endif
       qrcdo(i,k) = 0.
       qrcd(i,k) = 0.
     enddo
   enddo
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i)) then
         if(k.lt.jmin(i).and.k.ge.kbcon(i)) then
           dz = (zi(i,k+2) - zi(i,k+1))
           ptem = xlamdd-xlamde
           etad(i,k) = etad(i,k+1) * (1.-ptem * dz)
         elseif(k.lt.kbcon(i)) then
           dz = (zi(i,k+2) - zi(i,k+1))
           ptem = xlamd(i)+xlamdd-xlamde
           etad(i,k) = etad(i,k+1) * (1.-ptem * dz)
         endif
       endif
     enddo
   enddo
!
! downdraft moisture properties
!
   do i = its,ite
     if(cnvflg(i)) then
      pwevo(i) = 0.
     endif
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then 
       jmn = jmin(i)
       hcdo(i,jmn) = heo(i,jmn)
       qcdo(i,jmn) = qo(i,jmn)
       qrcdo(i,jmn) = qeso(i,jmn)
       ucdo(i,jmn) = uo(i,jmn)
       vcdo(i,jmn) = vo(i,jmn)
     endif
   enddo
!
   do k = kmax1,kts,-1 
     do i = its,ite 
       if (cnvflg(i) .and. k.lt.jmin(i)) then
         dz = zi(i,k+2) - zi(i,k+1)
         if(k.ge.kbcon(i)) then
           tem  = xlamde * dz
           tem1 = 0.5 * xlamdd * dz
         else
           tem  = xlamde * dz
           tem1 = 0.5 * (xlamd(i)+xlamdd) * dz
         endif
          factor = 1. + tem - tem1
          ptem  = 0.5 * tem - pgcon(i,k)
          ptem1 = 0.5 * tem + pgcon(i,k)
          hcdo(i,k) = ((1.-tem1)*hcdo(i,k+1)+tem*0.5*                          &
                      (heo(i,k)+heo(i,k+1)))/factor
          ucdo(i,k) = ((1.-tem1)*ucdo(i,k+1)+ptem*uo(i,k+1)                    &
                     +ptem1*uo(i,k))/factor
          vcdo(i,k) = ((1.-tem1)*vcdo(i,k+1)+ptem*vo(i,k+1)                    &
                     +ptem1*vo(i,k))/factor
          dbyo(i,k) = hcdo(i,k) - heso(i,k)
       endif
     enddo
   enddo
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.jmin(i)) then
         dq = qeso(i,k)
         dt = to(i,k)
         gamma = el2orc * dq / dt**2
         qrcdo(i,k) = dq+(1./hvap_)*(gamma/(1.+gamma))*dbyo(i,k)
         dz = zi(i,k+2) - zi(i,k+1)
         if(k.ge.kbcon(i)) then
           tem  = xlamde * dz
           tem1 = 0.5 * xlamdd * dz
         else
           tem  = xlamde * dz
           tem1 = 0.5 * (xlamd(i)+xlamdd) * dz
         endif
         factor = 1. + tem - tem1
         qcdo(i,k) = ((1.-tem1)*qcdo(i,k+1)+tem*0.5*                           &
                     (qo(i,k)+qo(i,k+1)))/factor
         pwdo(i,k) = etad(i,k+1) * qcdo(i,k) -etad(i,k+1) * qrcdo(i,k)
         qcdo(i,k) = qrcdo(i,k)
         pwevo(i) = pwevo(i) + pwdo(i,k)
       endif
     enddo
   enddo
!
! final downdraft strength dependent on precip
! efficiency (edt), normalized condensate (pwav), and
! evaporate (pwev)
!
   do i = its,ite
     edtmax = edtmaxl
     if(slimsk(i).eq.2.) edtmax = edtmaxs
     if(cnvflg(i)) then
       if(pwevo(i).lt.0.) then
         edto(i) = -edto(i) * pwavo(i) / pwevo(i)
         edto(i) = min(edto(i),edtmax)
       else
         edto(i) = 0.
       endif
     endif
   enddo
!
! downdraft cloudwork functions
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.jmin(i)) then
         gamma = el2orc * qeso(i,k) / to(i,k)**2
         dhh = hcdo(i,k)
         dt = to(i,k)
         dg = gamma
         dh = heso(i,k)
         dz = -1.*(zl(i,k+1)-zl(i,k))
         aa1(i) = aa1(i)+edto(i)*dz*(g_/(cp_*dt))*((dhh-dh)/(1.+dg))           &
                *(1.+fv_*cp_*dg*dt/hvap_)
         aa1(i) = aa1(i)+edto(i)*dz*g_*fv_*max(0.,(qeso(i,k)-qo(i,k)))
       endif
     enddo
   enddo
!
   do i = its,ite
     if(cnvflg(i).and.aa1(i).le.0.) cnvflg(i) = .false.
   enddo
!
   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return
!
! what would the change be, that a cloud with unit mass
! will do to the environment?
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i)) then
         dellah(i,k) = 0.
         dellaq(i,k) = 0.
         dellau(i,k) = 0.
         dellav(i,k) = 0.
       endif
     enddo
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then
       dp = 1000. * del(i,1)
       dellah(i,1) = edto(i) * etad(i,1) * (hcdo(i,1)                          &
                   - heo(i,1)) * g_ / dp
       dellaq(i,1) = edto(i) * etad(i,1) * (qcdo(i,1)                          &
                   - qo(i,1)) * g_ / dp
       dellau(i,1) = edto(i) * etad(i,1) * (ucdo(i,1)                          &
                   - uo(i,1)) * g_ / dp
       dellav(i,1) = edto(i) * etad(i,1) * (vcdo(i,1)                          &
                   - vo(i,1)) * g_ / dp
     endif
   enddo
!
! changed due to subsidence and entrainment
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.lt.ktcon(i)) then
         aup = 1.
         if(k.le.kb(i)) aup = 0.
         adw = 1.
         if(k.gt.jmin(i)) adw = 0.
         dv1 = heo(i,k)
         dv2 = .5 * (heo(i,k) + heo(i,k-1))
         dv3 = heo(i,k-1)
         dv1q = qo(i,k)
         dv2q = .5 * (qo(i,k) + qo(i,k-1))
         dv3q = qo(i,k-1)
         dv1u = uo(i,k)
         dv2u = .5 * (uo(i,k) + uo(i,k-1))
         dv3u = uo(i,k-1)
         dv1v = vo(i,k)
         dv2v = .5 * (vo(i,k) + vo(i,k-1))
         dv3v = vo(i,k-1)
         dp = 1000. * del(i,k)
         dz = zi(i,k+1) - zi(i,k)
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1))
         tem1 = xlamud(i)
         if(k.le.kbcon(i)) then
           ptem  = xlamde
           ptem1 = xlamd(i)+xlamdd
         else
           ptem  = xlamde
           ptem1 = xlamdd
         endif
!
         dellah(i,k) = dellah(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1               &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3               &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2*dz              &
         +  aup*tem1*eta(i,k-1)*.5*(hcko(i,k)+hcko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(hcdo(i,k)+hcdo(i,k-1))*dz) *g_/dp
!
         dellaq(i,k) = dellaq(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1q              &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3q              &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2q*dz             &
         +  aup*tem1*eta(i,k-1)*.5*(qcko(i,k)+qcko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(qrcdo(i,k)+qrcdo(i,k-1))*dz) *g_/dp
!
         dellau(i,k) = dellau(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1u              &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3u              &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2u*dz             &
         +  aup*tem1*eta(i,k-1)*.5*(ucko(i,k)+ucko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(ucdo(i,k)+ucdo(i,k-1))*dz          &
         - pgcon(i,k)*(aup*eta(i,k-1)-adw*edto(i)*etad(i,k))*(dv1u-dv3u))*g_/dp
!
         dellav(i,k) = dellav(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1v              &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3v              &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2v*dz             &
         +  aup*tem1*eta(i,k-1)*.5*(vcko(i,k)+vcko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(vcdo(i,k)+vcdo(i,k-1))*dz          &
         - pgcon(i,k)*(aup*eta(i,k-1)-adw*edto(i)*etad(i,k))*(dv1v-dv3v))*g_/dp
       endif
     enddo
   enddo
!
! cloud top
!
   do i = its,ite
     if(cnvflg(i)) then
       indx = ktcon(i)
       dp = 1000. * del(i,indx)
       dv1 = heo(i,indx-1)
       dellah(i,indx) = eta(i,indx-1) *                                        &
                        (hcko(i,indx-1) - dv1) * g_ / dp
       dv1q = qo(i,indx-1)
       dellaq(i,indx) = eta(i,indx-1) *                                        &
                        (qcko(i,indx-1) - dv1q) * g_ / dp
       dv1u = uo(i,indx-1)
       dellau(i,indx) = eta(i,indx-1) *                                        &
                        (ucko(i,indx-1) - dv1u) * g_ / dp
       dv1v = vo(i,indx-1)
       dellav(i,indx) = eta(i,indx-1) *                                        &
                        (vcko(i,indx-1) - dv1v) * g_ / dp
!
!  cloud water
!
       dellal(i,indx) = eta(i,indx-1) * qlko_ktcon(i) * g_ / dp
     endif
   enddo
!
! final changed variable per unit mass flux
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i).and.k.gt.ktcon(i)) then
         qo(i,k) = q1(i,k)
         to(i,k) = t1(i,k)
       endif
       if(cnvflg(i).and.k.le.ktcon(i)) then
         qo(i,k) = dellaq(i,k) * mbdt + q1(i,k)
         dellat  = (dellah(i,k) - hvap_ * dellaq(i,k)) / cp_
         to(i,k) = dellat * mbdt + t1(i,k)
         qo(i,k) = max(qo(i,k),1.0e-10)
       endif
     enddo
   enddo
!
!------------------------------------------------------------------------------
!
! the above changed environment is now used to calulate the
! effect the arbitrary cloud (with unit mass flux)
! which then is used to calculate the real mass flux,
! necessary to keep this change in balance with the large-scale
! destabilization.
!
! environmental conditions again
!
!------------------------------------------------------------------------------
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i)) then
         qeso(i,k)=0.01* fpvs(to(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k) / (p(i,k) + (eps-1.) * qeso(i,k))
         qeso(i,k) = max(qeso(i,k),qmin_)
!        tvo(i,k)  = to(i,k) + fv_ * to(i,k) * max(qo(i,k),qmin_)
       endif
     enddo
   enddo
!
! moist static energy
!
   do k = kts,kmax1
     do i = its,ite
       if(cnvflg(i)) then
         dz = .5 * (zl(i,k+1) - zl(i,k))
         dp = .5 * (p(i,k+1) - p(i,k))
         es = 0.01*fpvs(to(i,k+1),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         pprime = p(i,k+1) + (eps-1.) * es
         qs = eps * es / pprime
         dqsdp = - qs / pprime
         desdt = es * (fact1 / to(i,k+1) + fact2 / (to(i,k+1)**2))
         dqsdt = qs * p(i,k+1) * desdt / (es * pprime)
         gamma = el2orc * qeso(i,k+1) / (to(i,k+1)**2)
         dt = (g_ * dz + hvap_ * dqsdp * dp) / (cp_ * (1. + gamma))
         dq = dqsdt * dt + dqsdp * dp
         to(i,k) = to(i,k+1) + dt
         qo(i,k) = qo(i,k+1) + dq
         po = .5 * (p(i,k) + p(i,k+1))
         qeso(i,k) = 0.01* fpvs(to(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k) / (po + (eps-1.) * qeso(i,k))
         qeso(i,k) = max(qeso(i,k),qmin_)
         qo(i,k)   = max(qo(i,k), 1.0e-10)
         heo(i,k)  = .5 * g_ * (zl(i,k) + zl(i,k+1)) +                         &
                     cp_ * to(i,k) + hvap_ * qo(i,k)
         heso(i,k) = .5 * g_ * (zl(i,k) + zl(i,k+1)) +                         &
                     cp_ * to(i,k) + hvap_ * qeso(i,k)
       endif
     enddo
   enddo
!
   k = kmax
   do i = its,ite
     if(cnvflg(i)) then
       heo(i,k)  = g_ * zl(i,k) + cp_ * to(i,k) + hvap_ * qo(i,k)
       heso(i,k) = g_ * zl(i,k) + cp_ * to(i,k) + hvap_ * qeso(i,k)
     endif
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then
       xaa0(i) = 0.
       xpwav(i) = 0.
       indx = kb(i)
       xhkb(i) = heo(i,indx)
       xqkb(i) = qo(i,indx)
       hcko(i,indx) = xhkb(i)
       qcko(i,indx) = xqkb(i)
     endif
   enddo
!
! ..... static control .....
!
! moisture and cloud work functions
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.gt.kb(i).and.k.le.ktcon(i)) then
         dz = zi(i,k+1) - zi(i,k)
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz
         tem1 = 0.5 * xlamud(i) * dz
         factor = 1. + tem - tem1
         hcko(i,k) = ((1.-tem1)*hcko(i,k-1)+tem*0.5*                           &
                    (heo(i,k)+heo(i,k-1)))/factor
       endif
     enddo
   enddo
!
   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.gt.kb(i).and.k.lt.ktcon(i)) then
         alpha1 = min((-0.7*log(100.)+24.)*0.0001,c0)
         beta1 = 0.07
!
         if (to(i,k).gt.t0c_) then
           c0fac = alpha1
         else
           c0fac = alpha1*exp(beta1*(to(i,k)-t0c_))
         endif
!
         c0fac = max(0.0,c0fac)
         c0t(i,k) = c0fac
!
         dz = zi(i,k+1) - zi(i,k)
         gamma = el2orc * qeso(i,k) / (to(i,k)**2)
         xdby = hcko(i,k) - heso(i,k)
         xqrch = qeso(i,k)                                                     &
              + gamma * xdby / (hvap_ * (1. + gamma))
         tem  = 0.5 * (xlamb(i,k)+xlamb(i,k-1)) * dz
         tem1 = 0.5 * xlamud(i) * dz
         factor = 1. + tem - tem1
         qcko(i,k) = ((1.-tem1)*qcko(i,k-1)+tem*0.5*(qo(i,k)+qo(i,k-1)))/factor
         dq = eta(i,k) * qcko(i,k) - eta(i,k) * xqrch
         if(k.ge.kbcon(i).and.dq.gt.0.) then
           etah = .5 * (eta(i,k) + eta(i,k-1))
           if(ncloud.gt.0..and.k.gt.jmin(i)) then
             qlk = dq / (eta(i,k) + etah * (c0t(i,k) + c1t(i,k)) * dz)
           else
             qlk = dq / (eta(i,k) + etah * c0t(i,k) * dz)
           endif
           xpw = etah * c0t(i,k) * dz * qlk
           if(k.lt.ktcon1(i)) then
             xaa0(i) = xaa0(i) - (zl(i,k+1) - zl(i,k)) * g_ * qlk
           endif
           qcko(i,k) = qlk + xqrch
           xpwav(i) = xpwav(i) + xpw
         endif
       endif
!
       if(cnvflg(i).and.k.ge.kbcon(i).and.k.lt.ktcon1(i)) then
         dz1 = zl(i,k+1) - zl(i,k)
         gamma = el2orc * qeso(i,k) / (to(i,k)**2)
         rfact =  1. + fv_ * cp_ * gamma                                       &
                  * to(i,k) / hvap_
         xdby = hcko(i,k) - heso(i,k)
         xaa0(i) = xaa0(i)                                                     &
                 + dz1 * (g_ / (cp_ * to(i,k)))                                &
                 * xdby / (1. + gamma)                                         &
                 * rfact
         xaa0(i)=xaa0(i)+                                                      &
                  dz1 * g_ * fv_ *                                             &
                  max(0.,(qeso(i,k) - qo(i,k)))
       endif
     enddo
   enddo
!
! ..... downdraft calculations .....
!
! downdraft moisture properties
!
   do i = its,ite
     xpwev(i) = 0.
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then
       jmn = jmin(i)
       xhcd(i,jmn) = heo(i,jmn)
       xqcd(i,jmn) = qo(i,jmn)
       qrcd(i,jmn) = qeso(i,jmn)
     endif
   enddo
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.jmin(i)) then
         dz = zi(i,k+2) - zi(i,k+1)
         if(k.ge.kbcon(i)) then
            tem  = xlamde * dz
            tem1 = 0.5 * xlamdd * dz
         else
            tem  = xlamde * dz
            tem1 = 0.5 * (xlamd(i)+xlamdd) * dz
         endif
         factor = 1. + tem - tem1
         xhcd(i,k) = ((1.-tem1)*xhcd(i,k+1)+tem*0.5*                           &
                    (heo(i,k)+heo(i,k+1)))/factor
       endif
     enddo
   enddo
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.jmin(i)) then
         dq = qeso(i,k)
         dt = to(i,k)
         gamma = el2orc * dq / dt**2
         dh = xhcd(i,k) - heso(i,k)
         qrcd(i,k) = dq+(1./hvap_)*(gamma/(1.+gamma))*dh
         dz = zi(i,k+2) - zi(i,k+1)
         if(k.ge.kbcon(i)) then
           tem  = xlamde * dz
           tem1 = 0.5 * xlamdd * dz
         else
           tem  = xlamde * dz
           tem1 = 0.5 * (xlamd(i)+xlamdd) * dz
         endif
         factor = 1. + tem - tem1
         xqcd(i,k) = ((1.-tem1)*xqcd(i,k+1)+tem*0.5*                           &
                   (qo(i,k)+qo(i,k+1)))/factor
         xpwd     = etad(i,k+1) * (xqcd(i,k) - qrcd(i,k))
         xqcd(i,k)= qrcd(i,k)
         xpwev(i) = xpwev(i) + xpwd
       endif
     enddo
   enddo
!
   do i = its,ite
     edtmax = edtmaxl
     if(slimsk(i).eq.2.) edtmax = edtmaxs
     if(cnvflg(i)) then
       if(xpwev(i).ge.0.) then
         edtx(i) = 0.
       else
         edtx(i) = -edtx(i) * xpwav(i) / xpwev(i)
         edtx(i) = min(edtx(i),edtmax)
       endif
     endif
   enddo
!
! downdraft cloudwork functions
!
   do k = kmax1,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.jmin(i)) then
         gamma = el2orc * qeso(i,k) / to(i,k)**2
         dhh = xhcd(i,k)
         dt = to(i,k)
         dg = gamma
         dh = heso(i,k)
         dz =-1.*(zl(i,k+1)-zl(i,k))
         xaa0(i) = xaa0(i)+edtx(i)*dz*(g_/(cp_*dt))*((dhh-dh)/(1.+dg))         &
                 *(1.+fv_*cp_*dg*dt/hvap_)
         xaa0(i) = xaa0(i)+edtx(i)*                                            &
                   dz*g_*fv_*max(0.,(qeso(i,k)-qo(i,k)))
       endif
     enddo
   enddo
!
! calculate critical cloud work function
!
   do i = its,ite
     tem = zi(i,ktcon1(i)) - zi(i,kbcon1(i))
     dtconv(i) = tfac * tem / wc(i)
     dtconv(i) = max(dtconv(i),dtmin)
     dtconv(i) = min(dtconv(i),dtmax)
!    dtconv(i) = max(1800., dt2)
   enddo
!
! large scale forcing
!
! compute mean velocity between kb kbcon
!
   do i = its,ite
     if (cnvflg(i).and.slimsk(i).eq.2.) then
       wc(i) = 0.
       sumx(i) = 0.
     endif
   enddo
!
   do k = kts,kbmax
     do i = its,ite
       if (cnvflg(i).and.slimsk(i).eq.2.) then
         if (k.gt.kb(i) .and. k.le.kbcon(i)) then
           dz = zi(i,k+1) - zi(i,k)
           tem = sqrt(uo(i,k)**2 + vo(i,k)**2)
           wc(i) = wc(i) + tem * dz
           sumx(i) = sumx(i) + dz
         endif
       endif
     enddo
   enddo
!
   do i = its,ite
     if (cnvflg(i).and.slimsk(i).eq.2.) then
       wc(i) = wc(i) / sumx(i)
       dtpbl(i) = zl(i,kbcon(i))/wc(i)
     else
       dtpbl(i) = dtconv(i)
     endif
   enddo
!
   do i = its,ite
     if (cnvflg(i)) then
       apbl(i) = g_ * (hpbl(i)-hpbl_hold(i))/dt2 * dtpbl(i)
       apbl(i) = min(max(apbl(i),0.0),aa1(i))
     endif
   enddo
!
   do i = its,ite
     if(cnvflg(i)) then
       f(i) = (aa1(i) - apbl(i)) / dtconv(i)
       if(f(i).le.0.) cnvflg(i) = .false.
     endif
     if(cnvflg(i)) then
       xk(i) = (xaa0(i) - aa1(i)) / mbdt
       if(xk(i).ge.0.) cnvflg(i) = .false.
     endif
!
! kernel, cloud base mass flux
!
     if(cnvflg(i)) then
       xmb(i) = -f(i) / xk(i)
       xmb(i) = xmb(i) * clear(i) * (1.-sigma)
       xmb(i) = min(xmb(i),xmbmax(i))
     endif
     pden(i) = p(i,kbcon(i))/to(i,kbcon(i))/rd_
     pdot(i) = 10.* dot(i,kbcon(i))
!    if (pden(i)*pdot(i).gt.xmb(i)) cnvflg(i) = .false.
     if (xmb(i).lt.pdot(i)/g_) cnvflg(i) = .false.
   enddo
   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return
!
! restore t0 and qo to t1 and q1 in case convection stops
!
   do k = kts,kmax
     do i = its,ite
       if (cnvflg(i)) then
         to(i,k) = t1(i,k)
         qo(i,k) = q1(i,k)
         uo(i,k) = u1(i,k)
         vo(i,k) = v1(i,k)
         qeso(i,k) = 0.01*fpvs(t1(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k) / (p(i,k) + (eps-1.) * qeso(i,k))
         qeso(i,k) = max(qeso(i,k),qmin_)
       endif
     enddo
   enddo
!
! feedback: simply the changes from the cloud with unit mass flux
!           multiplied by  the mass flux necessary to keep the
!           equilibrium with the larger-scale.
!
   do i = its,ite
     delhbar(i) = 0.
     delqbar(i) = 0.
     deltbar(i) = 0.
     qcond(i) = 0.
     delubar(i) = 0.
     delvbar(i) = 0.
   enddo
!
   do k = kts,kmax
     do i = its,ite
       if (cnvflg(i).and.k.le.ktcon(i).and.dellaq(i,k).le.0.) then
         if (q1(i,k).gt.0.) then
           tem = dellaq(i,k) * xmb(i) * dt2
           dellaq(i,k) = max(tem,-q1(i,k))/(xmb(i)*dt2)
         else
           dellaq(i,k) = 0.0
         endif
       endif
     enddo
   enddo
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i).and.k.le.ktcon(i)) then
         dellat = (dellah(i,k) - hvap_ * dellaq(i,k)) / cp_
         t1(i,k) = t1(i,k) + dellat * xmb(i) * dt2
         q1(i,k) = q1(i,k) + dellaq(i,k) * xmb(i) * dt2
         tem=1./rcs
         u1(i,k) = u1(i,k) + dellau(i,k) * xmb(i) * dt2 * tem
         v1(i,k) = v1(i,k) + dellav(i,k) * xmb(i) * dt2 * tem 
         dp = 1000. * del(i,k)
         delhbar(i) = delhbar(i) + dellah(i,k)*xmb(i)*dp/g_
         delqbar(i) = delqbar(i) + dellaq(i,k)*xmb(i)*dp/g_
         deltbar(i) = deltbar(i) + dellat*xmb(i)*dp/g_
         delubar(i) = delubar(i) + dellau(i,k)*xmb(i)*dp/g_
         delvbar(i) = delvbar(i) + dellav(i,k)*xmb(i)*dp/g_
       endif
     enddo
   enddo
!
   do k = kts,kmax 
     do i = its,ite 
       if (cnvflg(i) .and. k.le.ktcon(i)) then
         qeso(i,k)=0.01* fpvs(t1(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k)/(p(i,k) + (eps-1.)*qeso(i,k))
         qeso(i,k) = max(qeso(i,k), qmin_)
       endif
     enddo
   enddo
!
   do i = its,ite 
     rntot(i) = 0.
     delqev(i) = 0.
     delq2(i) = 0.
     flg(i) = cnvflg(i) 
   enddo
!
!  comptute rainfall  
!
   do k = kmax,kts,-1
     do i = its,ite
       if(cnvflg(i).and.k.lt.ktcon(i)) then
         aup = 1.
         if(k.le.kb(i)) aup = 0.
         adw = 1.
         if(k.ge.jmin(i)) adw = 0.
         rntot(i) = rntot(i)                                                   &
               + (aup * pwo(i,k) + adw * edto(i) * pwdo(i,k))                  &
               * xmb(i) * .001 * dt2
       endif
     enddo
   enddo
!
!  conversion rainfall (m) and compute the evaporation of falling raindrops 
!
   do k = kmax,kts,-1
     do i = its,ite
       delq(i) = 0.0
       deltv(i) = 0.0
       qevap(i) = 0.0
       if(cnvflg(i).and.k.lt.ktcon(i)) then
         aup = 1.
         if(k.le.kb(i)) aup = 0.
         adw = 1.
         if(k.ge.jmin(i)) adw = 0.
         rain(i) = rain(i)                                                     &
               + (aup * pwo(i,k) + adw * edto(i) * pwdo(i,k))                  &
               * xmb(i) * .001 * dt2
         qrsk(i,k) = aup * pwo(i,k) + adw * edto(i) * pwdo(i,k)
       endif
!
       if(cnvflg(i).and.flg(i).and.k.lt.ktcon(i)) then
         ccn_f = 1.0
         evef = edt_s(i) * evfacts * ccn_f
         if(slimsk(i).eq.1.) evef = edt_s(i) * evfactl * ccn_f
         qcond(i) = evef * (q1(i,k) - qeso(i,k)) / (1. + el2orc *              &
                  qeso(i,k) / t1(i,k)**2)
         dp = 1000. * del(i,k)
         if(rain(i).gt.0..and.qcond(i).lt.0.) then
           qevap(i) = -qcond(i) * (1. - exp(-.32 * sqrt(dt2 * rain(i))))
           qevap(i) = min(qevap(i), rain(i)*1000.*g_/dp)
           delq2(i) = delqev(i) + .001 * qevap(i) * dp / g_
           if (delq2(i).gt.rntot(i)) then
             qevap(i) = 1000.* g_ * (rntot(i) - delqev(i)) / dp
             flg(i) = .false.
           endif 
         endif
         if(rain(i).gt.0..and.qevap(i).gt.0.) then
           q1(i,k) = q1(i,k) + qevap(i)
           t1(i,k) = t1(i,k) - (hvap_/cp_) * qevap(i)
           rain(i) = rain(i) - .001 * qevap(i) * dp / g_
           delqev(i) = delqev(i) + .001*dp*qevap(i)/g_
           deltv(i) =  - (hvap_/cp_)*qevap(i)/dt2
           delq(i) =  + qevap(i)/dt2
         endif
         dellaq(i,k) = dellaq(i,k) + delq(i)/xmb(i)
         delqbar(i)  = delqbar(i) + delq(i)*dp/g_
         deltbar(i)  = deltbar(i) + deltv(i)*dp/g_
       endif
!
       if (cnvflg(i).and.k.lt.ktcon(i)) then
         qrs(i,k) = max(qrsk(i,k) - max(qevap(i),0.),0.)
         qci(i,k) = max(qcirs(i,k) - aup*pwo(i,k),0.)
       endif
     enddo
   enddo
!
! consider the negative rain in the event of rain evaporation and downdrafts
!
   do i = its,ite
     if(cnvflg(i)) then
       if(rain(i).lt.0..and..not.flg(i)) rain(i) = 0.
       if(rain(i).le.0.) then
         rain(i) = 0.
       else
         ktop(i) = ktcon(i)
         kbot(i) = kbcon(i)
         icps(i) = 1
       endif
     endif
   enddo
!
   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i).and.rain(i).le.0.) then
          t1(i,k) = to(i,k)
          q1(i,k) = qo(i,k)
          u1(i,k) = uo(i,k)
          v1(i,k) = vo(i,k)
       endif
     enddo
   enddo
!
!  detrainment of cloud water and ice
!
   if (ncloud.gt.0) then
     do k = kts,kmax 
       do i = its,ite 
         if (cnvflg(i) .and. rain(i).gt.0.) then
           if (k.ge.kbcon(i).and.k.le.ktcon(i)) then
             tem  = dellal(i,k) * xmb(i) * dt2
             tem1 = max(0.0, min(1.0, (tcr-t1(i,k))*tcrf))
             if (ncloud.ge.2) then
               qi2(i,k) = qi2(i,k) + tem * tem1            ! ice
               qc2(i,k) = qc2(i,k) + tem *(1.0-tem1)       ! water
             else
               qc2(i,k) = qc2(i,k) + tem
             endif
           endif
         endif
       enddo
     enddo
   endif
!
   end subroutine nsas2d

! add subroutine

 subroutine trigger_ntdk( its, ite, kts, kte, rpten, rpren, rpgeo, rpaph, rpgeoh,& !cuinit input ! jhsim
                         rpap,& !cutypen input
     &      cpd, rd, rv, alv, als,g,& !constant input
     &      kb_heo, cubot, cutop, kdpl, ldcum) !out variables
      implicit none
! constant input
      real     cpd, rd, rv, alv, als, g, alf

! cuinit input
      integer  klon, klev, klevp1, klevm1
      integer  its, ite, kts, kte !jhsim
      real     rpten(its:ite,kts:kte),        rpren(its:ite,kts:kte),&
     &         rpgeo(its:ite,kts:kte)
      real     rpaph(its:ite,kts:kte+1), rpgeoh(its:ite,kts:kte+1)

! cutypen input
      real     rpap(its:ite,kts:kte)

! cutype local variables
      integer  nk,is,ikb,ikt,levels
      integer  kctop(its:ite),kcbot(its:ite)
      integer  zcbase(its:ite), itoppacel(its:ite)
      integer  klab(its:ite,kts:kte)


      real     ptu(its:ite,kts:kte), pqu(its:ite,kts:kte), dhen(its:ite,kts:kte), dh(its:ite,kts:kte),&
     &         kup(its:ite,kts:kte), vptu(its:ite,kts:kte), vten(its:ite,kts:kte), zbuo(its:ite,kts:kte), abuoy(its:ite,kts:kte)

      real     plu(its:ite,kts:kte) !jhsim
      real     zqold(its:ite), wbase(its:ite)
      real     eta(its:ite),dz(its:ite),coef(its:ite)
      real     tmix,zmix,qmix,pmix
      real     dp, zrg, zdq, zlglac, ralfdcp, zdnoprc

      real     fscale
      real     atop1,atop2,abot
      real     zqsu, zalfaw, zfacw, zfaci, zfac, zesdp, zdqsdt, zdtdp, zdp
      real     zpdifftop, zpdiffbot
      real tmelt, c3les, c3ies, c4les, c4ies, c5les, c5ies
      logical  loflag(its:ite), deepflag(its:ite),  resetflag(its:ite), lldcum(its:ite), needreset

! local variables
      integer  j, k, ik, icall, zz, pp
      real     vtmpc1, zqs, zew, zcor, tt, rcpd, zzs
      real     deltt, deltq
      real     zph(its:ite)
      real     pqsen(its:ite,kts:kte), pqen(its:ite,kts:kte),&
      &        ptenh(its:ite,kts:kte), pqenh(its:ite,kts:kte),&
      &        pqsenh(its:ite,kts:kte)
      real     pten(its:ite,kts:kte),        pren(its:ite,kts:kte),&
     &         pgeo(its:ite,kts:kte), pap(its:ite,kts:kte)
      real     paph(its:ite,kts:kte+1), pgeoh(its:ite,kts:kte+1)


! out variables
      integer  cubot(its:ite), cutop(its:ite), kdpl(its:ite)
      real     kb_heo(its:ite) ! jhchoi
      logical  ldcum(its:ite)
!

      klev   = kte - kts + 1 ! jhsim
      klevp1 = klev + 1      ! jhsim
      klevm1 = klev - 1      ! jhsim

      do j=its,ite
         cutop(j)     = 0 !jhsim
         cubot(j)     = 0 !jhsim
         kctop(j)     = 0
         kcbot(j)     = 0
         kdpl(j)      = klev     !jhsim
         wbase(j)     = 0.       !jhsim
         ldcum(j)     = .false.  !jhsim
         kb_heo(j)    = 0. !jhsim
      end do


      alf     = 3.50E5
      vtmpc1  = rv/rd-1.0
      rcpd    = 1./cpd
      zrg     = 1.0/g
      ralfdcp = alf*rcpd
      zdnoprc = 2.0e4
      tmelt   = 273.16
      c3les   = 17.2693882
      c3ies   = 21.875
      c4les   = 35.86
      c4ies   = 7.66
      c5les   = c3les*(tmelt-c4les)
      c5ies   = c3ies*(tmelt-c4ies)
      !
      !---------------------------------------  
      !

      !---------------------------------------
      ! revised by hjbae
      !--------------------------------------
      !pp = 0
      do k=kts,kte
        !zz = klev-pp
        zz = klev - (k - 1)
        do j=its,ite
          pten(j,zz) = rpten(j,k)
          pgeo(j,zz) = rpgeo(j,k)
          pren(j,zz) = rpren(j,k)
          pap(j,zz)  = rpap(j,k)
        enddo
        !pp = pp + 1
      enddo

      !pp = 0
      do k=kts,kte+1
        !zz = klevp1-pp
        zz = klevp1 - (k - 1)
        do j=its,ite
          pgeoh(j,zz) = rpgeoh(j,k)
          paph(j,zz)  = rpaph(j,k)
        enddo
        !pp = pp + 1
      enddo

      do k=kts,kte
        do j=its,ite
              pqen(j,k) = pren(j,k)/(1.0+pren(j,k))
              tt=pten(j,k)
              zew=foeewm(tt,rv,rd)
              zqs=zew/pap(j,k)
              zqs=min(0.5,zqs)
              zcor=1./(1.-vtmpc1*zqs)
              pqsen(j,k)=zqs*zcor
        end do
      end do
      !----------------------------------------------------------------
      !
      !----------------------------------------------------------------
      do k=kts+1,kte
        do j=its,ite
          ptenh(j,k)=(max(cpd*pten(j,k-1)+pgeo(j,k-1), &
      &             cpd*pten(j,k)+pgeo(j,k))-pgeoh(j,k))*rcpd
          pqenh(j,k) = pqen(j,k-1)
          pqsenh(j,k)= pqsen(j,k-1)
          zph(j)=paph(j,k)
          loflag(j)=.true.
        end do

        if ( k >= klev-1 .or. k < 2 ) cycle
        ik=k
        icall=0
        call cuadjtqn(its,ite,kts,kte,ik,zph,ptenh,pqsenh,loflag,icall,rv,rd,alv,als,rcpd)
        do j=its,ite
          pqenh(j,k)=min(pqen(j,k-1),pqsen(j,k-1)) &
      &            +(pqsenh(j,k)-pqsen(j,k-1))
          pqenh(j,k)=max(pqenh(j,k),0.)
        end do
      end do

      do j=its,ite
        ptenh(j,kte)=(cpd*pten(j,kte)+pgeo(j,kte)- &
      &               pgeoh(j,kte))*rcpd
        pqenh(j,kte)=pqen(j,kte)
        ptenh(j,1)=pten(j,1)
        pqenh(j,1)=pqen(j,1)
      end do

      do k=klevm1,2,-1
        do j=its,ite
          zzs=max(cpd*ptenh(j,k)+pgeoh(j,k), &
      &        cpd*ptenh(j,k+1)+pgeoh(j,k+1))
          ptenh(j,k)=(zzs-pgeoh(j,k))*rcpd
        end do
      end do
      !
      !-----------------------------------------------------------
      !


      !-----------------------------------------------------------
      ! next, let's check the deep convection
      ! the first level is klevm1-1
      ! define deltat and deltaq
      !----------------------------------------------------------
      ! we check the parcel starting level by level
      ! assume the mix-layer is 60hPa
      deltt = 0.2
      deltq = 1.0e-4
      do j=its,ite
        deepflag(j) = .false.
      end do !! deepflag 초기화

      do k=kte,kts,-1
        do j=its,ite
          if((paph(j,klev+1)-paph(j,k)) .lt. 350.e2) itoppacel(j) = k
        end do
      end do ! looks for weakly entraining deep convection originating in the lowest 350 hPa

      do levels=klevm1-1,klev/2+1,-1 ! loop starts
        do k=kts,kte
          do j=its,ite
            plu(j,k)   = 0.0  ! parcel liquid water
            ptu(j,k)   = 0.0  ! parcel temperature
            pqu(j,k)   = 0.0  ! parcel specific humidity
            dh(j,k)    = 0.0  ! parcel dry static energy
            dhen(j,k)  = 0.0  ! environment dry static energy
            kup(j,k)   = 0.0  ! updraught kinetic energy for parcel
            vptu(j,k)  = 0.0  ! parcel virtual temperature considering water-loading
            vten(j,k)  = 0.0  ! environment virtual temperature
            abuoy(j,k) = 0.0
            zbuo(j,k)  = 0.0
            klab(j,k)  = 0
          end do
        end do !! 변수 초기화

        do j=its,ite
          kcbot(j)     = levels
          kctop(j)     = levels
          zqold(j)     = 0.
          lldcum(j)    = .false.
          resetflag(j) = .false.
          loflag(j)    = (.not. deepflag(j)) .and. (levels.ge.itoppacel(j))
        end do !! 변수 초기화 및 loflag 결정

        ! start the inner loop to search the deep convection points
        do k=levels,2,-1 !k loop
          is=0
          do j=its,ite
            if(loflag(j))then
              is=is+1
            endif
          enddo
          if(is.eq.0) exit !!k loop exit

          ! define the variables at the departure level 
          if(k .eq. levels) then
            do j=its,ite
              if(loflag(j)) then
                if((paph(j,klev+1)-paph(j,k)) < 60.e2) then !! mix-layer
                  tmix = 0.
                  qmix = 0.
                  zmix = 0.
                  pmix = 0.
                  do nk=k+2,k,-1
                    if(pmix < 50.e2) then
                      dp   = paph(j,nk) - paph(j,nk-1)
                      tmix = tmix+dp*ptenh(j,nk)
                      qmix = qmix+dp*pqenh(j,nk)
                      zmix = zmix+dp*pgeoh(j,nk)
                      pmix = pmix+dp
                    end if
                  end do
                  tmix = tmix/pmix
                  qmix = qmix/pmix
                  zmix = zmix/pmix
                else
                  tmix = ptenh(j,k+1)
                  qmix = pqenh(j,k+1)
                  zmix = pgeoh(j,k+1)
                end if
                pqu(j,k+1)  = qmix + deltq !! initial moisture perturbation (Bechtold et al., 2004)
                dhen(j,k+1) = zmix + tmix*cpd
                dh(j,k+1)   = dhen(j,k+1) + deltt*cpd !! initial temperature perturbation (Bechtold et al., 2004)
                ptu(j,k+1)  = (dh(j,k+1)-pgeoh(j,k+1))*rcpd
                kup(j,k+1)  = 0.5
                klab(j,k+1) = 1
                vptu(j,k+1) = ptu(j,k+1)*(1.+vtmpc1*pqu(j,k+1))
                vten(j,k+1) = ptenh(j,k+1)*(1.+vtmpc1*pqenh(j,k+1))
                zbuo(j,k+1) = (vptu(j,k+1)-vten(j,k+1))/vten(j,k+1)
                kb_heo(j) = dh(j,k+1) + alv * pqu(j,k+1) !jhchoi
              end if
            end do
          end if

          ! the next levels, we use the variables at the first level as initial values
          do j=its,ite
            if(loflag(j)) then
              fscale    = min(1.,(pqsen(j,k)/pqsen(j,levels))**3)
              eta(j)    = 1.75e-3*fscale  !! deep convection entrainment rate (Zhang and Wang, 2017)
              dz(j)     = (pgeoh(j,k)-pgeoh(j,k+1))*zrg
              coef(j)   = 0.5*eta(j)*dz(j)
              dhen(j,k) = pgeoh(j,k) + cpd*ptenh(j,k)
              dh(j,k)   = (coef(j)*(dhen(j,k+1)+dhen(j,k))&
                          & +(1.-coef(j))*dh(j,k+1))/(1.+coef(j))
              pqu(j,k)  = (coef(j)*(pqenh(j,k+1)+pqenh(j,k))&
                          & +(1.-coef(j))*pqu(j,k+1))/(1.+coef(j))
              ptu(j,k)  = (dh(j,k)-pgeoh(j,k))*rcpd
              zqold(j)  = pqu(j,k)
              zph(j)    = paph(j,k)
            end if
          end do ! entrainment with next levels

          ! check if the parcel is saturated
          ik=k
          icall=1
          call cuadjtqn(its,ite,kts,kte,ik,zph,ptu,pqu,loflag,icall,rv,rd,alv,als,rcpd)
          do j=its,ite
            if( loflag(j) ) then
              zdq        = max((zqold(j) - pqu(j,k)),0.) ! jhsim

              plu(j,k)   = plu(j,k+1) + zdq ! q와 q_s의 차이를 아래층에 더해줌
              zlglac     = zdq*((1.-foealfa(ptu(j,k))) - &
                          (1.-foealfa(ptu(j,k+1))))
              plu(j,k)   = 0.5*plu(j,k)     ! Deep

              dh(j,k)    = pgeoh(j,k) + cpd*(ptu(j,k)+ralfdcp*zlglac) ! DSE 조정
              ! compute the updraft speed
              vptu(j,k)  = ptu(j,k)*(1.+vtmpc1*pqu(j,k)-plu(j,k))+&
                          ralfdcp*zlglac
              vten(j,k)  = ptenh(j,k)*(1.+vtmpc1*pqenh(j,k))
              zbuo(j,k)  = (vptu(j,k) - vten(j,k))/vten(j,k) !! parcel t < env t = -buoyancy
              abuoy(j,k) = (zbuo(j,k)+zbuo(j,k+1))*0.5*g
              atop1      = 1.0 - 2.*coef(j)
              atop2      = 2.0*dz(j)*abuoy(j,k)
              abot       = 1.0 + 2.*coef(j)
              kup(j,k)   = (atop1*kup(j,k+1) + atop2) / abot !! 아래층 kup 고려
              ! let's find the exact cloud base
              if ( plu(j,k) > 0. .and. klab(j,k+1) == 1 ) then ! liquid water가 있는지 확인
                ik        = k + 1
                zqsu      = foeewm(ptu(j,ik),rv,rd)/paph(j,ik)
                zqsu      = min(0.5,zqsu)
                zcor      = 1./(1.-vtmpc1*zqsu)
                zqsu      = zqsu*zcor !q_s
                zdq       = min(0.,pqu(j,ik)-zqsu)
                zalfaw    = foealfa(ptu(j,ik))
                zfacw     = c5les/((ptu(j,ik)-c4les)**2)
                zfaci     = c5ies/((ptu(j,ik)-c4ies)**2)
                zfac      = zalfaw*zfacw + (1.-zalfaw)*zfaci
                zesdp     = foeewm(ptu(j,ik),rv,rd)/paph(j,ik)
                zcor      = 1./(1.-vtmpc1*zesdp)
                zdqsdt    = zfac*zcor*zqsu
                zdtdp     = rd*ptu(j,ik)/(cpd*paph(j,ik))
                zdp       = zdq/(zdqsdt*zdtdp) ! parcel이 포화상태일 때, 압력차이
                zcbase(j) = paph(j,ik) + zdp ! cloud base pressure
                ! chose nearest half level as cloud base (k or k+1)
                zpdifftop = zcbase(j) - paph(j,k)
                zpdiffbot = paph(j,k+1) - zcbase(j)
                if ( zpdifftop > zpdiffbot .and. kup(j,k+1) > 0. ) then
                  ikb         = min(klev-1,k+1)
                  klab(j,ikb) = 2
                  klab(j,k)   = 2
                  kcbot(j)    = ikb
                  plu(j,k+1)  = 1.0e-8
                else if ( zpdifftop <= zpdiffbot .and.kup(j,k) > 0. ) then
                  klab(j,k) = 2
                  kcbot(j)  = k
                end if
              end if

              if(kup(j,k) .lt. 0.)then ! 하강 기류면 k out
                loflag(j) = .false.
                if(plu(j,k+1) .gt. 0.) then ! 하강 기류 아래층이 cloud top
                  kctop(j) = k
                  lldcum(j) = .true.
                else
                  lldcum(j) = .false.
                end if
              else
                if(plu(j,k) .gt. 0.)then
                  klab(j,k)=2 ! cloud base not detecting
                else
                  klab(j,k)=1
                end if
              end if
            end if
          end do
        end do !k loop end
       !   ???? hjbae 
        needreset = .false.
        do j=its,ite
          ikb = kcbot(j)
          ikt = kctop(j)
          if(paph(j,ikb) - paph(j,ikt) < zdnoprc) lldcum(j) = .false.
          if(lldcum(j)) then
            ldcum(j)     = .true.
            deepflag(j)  = .true.
            wbase(j)     = sqrt(max(2.*kup(j,ikb),0.)) !cbase w
            needreset    = .true.
            resetflag(j) = .true.
            cubot(j)     = ikb
            cutop(j)     = ikt
            kdpl(j)      = levels+1
          end if
        end do
      end do ! levels loop end

      do j=its,ite
        cubot(j) = klevp1 - cubot(j)
        cutop(j) = klevp1 - cutop(j)
        kdpl(j)  = klevp1 - kdpl(j)
         print*, j,ldcum(j),cubot(j),cutop(j),kdpl(j),kb_heo(j),klevp1
      end do

      !cubot = 11
      !cutop = 17
      !kdpl  = 11        
      !kb_heo = 332529


!디버깅 메시지: 주요 작업 완료 확인
  !print *, 'trigger_ntdk: Completed main loop over klev'

      end subroutine trigger_ntdk

     subroutine cuadjtqn                 &
     &    (its,ite,kts,kte, kk, psp, pt, pq, ldflag, kcall, rv,rd,alv,als,rcpd)
!          m.tiedtke         e.c.m.w.f.     12/89     
!          purpose.                                                                 
!          --------                                                                 
!          to produce t,q and l values for cloud ascent                             

!          interface                                                                
!          ---------                                                                
!          this routine is called from subroutines:                                 
!              *cond*     (t and q at condensation level)                           
!              *cubase*   (t and q at condensation level)                           
!              *cuasc*    (t and q at cloud levels)                                 
!              *cuini*    (environmental t and qs values at half levels)            
!          input are unadjusted t and q values,                                     
!          it returns adjusted values of t and q                                    

!     parameter     description                                   units             
!     ---------     -----------                                   -----             
!     input parameters (integer):                                                   

!    *klon*         number of grid points per packet                                
!    *klev*         number of levels                                                
!    *kk*           level                                                           
!    *kcall*        defines calculation as                                          
!                      kcall=0  env. t and qs in*cuini*                             
!                      kcall=1  condensation in updrafts  (e.g. cubase, cuasc)      
!                      kcall=2  evaporation in downdrafts (e.g. cudlfs,cuddraf)     
!     input parameters (real):                                                      

!    *psp*          pressure                                        pa              

!     updated parameters (real):                                                    

!    *pt*           temperature                                     k               
!    *pq*           specific humidity                             kg/kg             
!          externals                                                                
!          ---------                                                                
!          for condensation calculations.                                           
!          the tables are initialised in *suphec*.                                  

!----------------------------------------------------------------------             

      implicit none

      integer  klev,klon
      integer  its,ite,kts,kte !jhsim

      real     pt(its:ite,kts:kte),          pq(its:ite,kts:kte),  &
     &         psp(its:ite)
      logical  ldflag(its:ite)
! local variables
      integer  j
      integer   kcall,kk
      real     zqmax,zqsat,zcor,zqp,zcond,zcond1,zl,zi,zf,rv,rd,alv,als,rcpd,vtmpc1
      real     tmelt, c2es, c3les, c3ies, c4les, c4ies, c5les, c5ies, r5alvcp, r5alscp
!----------------------------------------------------------------------             
!     1.           define constants                                                 
!                  ----------------                                                 
      zqmax=0.5
      vtmpc1=rv/rd-1.0


      tmelt=273.16
      c2es=610.78*rd/rv
      c3les=17.2693882
      c3ies=21.875
      c4les=35.86
      c4ies=7.66
      c5les=c3les*(tmelt-c4les)
      c5ies=c3ies*(tmelt-c4ies)
      r5alvcp=c5les*alv*rcpd
      r5alscp=c5ies*als*rcpd
!     2.           calculate condensation and adjust t and q accordingly            
!                  -----------------------------------------------------            
      if ( kcall == 1 ) then
        do j = its,ite
          if ( ldflag(j) ) then
            zqp = 1./psp(j)
            zl = 1./(pt(j,kk)-c4les)
            zi = 1./(pt(j,kk)-c4ies)
            zqsat = c2es*(foealfa(pt(j,kk))*exp(c3les*(pt(j,kk)-tmelt)*zl) + &
                  (1.-foealfa(pt(j,kk)))*exp(c3ies*(pt(j,kk)-tmelt)*zi))
            zqsat = zqsat*zqp
            zqsat = min(0.5,zqsat)
            zcor = 1. - vtmpc1*zqsat
            zf = foealfa(pt(j,kk))*r5alvcp*zl**2 + &
                 (1.-foealfa(pt(j,kk)))*r5alscp*zi**2
            zcond = (pq(j,kk)*zcor**2-zqsat*zcor)/(zcor**2+zqsat*zf)
            if ( zcond > 0. ) then
              pt(j,kk) = pt(j,kk) + foeldcpm(pt(j,kk),alv,als,rcpd)*zcond
              pq(j,kk) = pq(j,kk) - zcond
              zl = 1./(pt(j,kk)-c4les)
              zi = 1./(pt(j,kk)-c4ies)
              zqsat = c2es*(foealfa(pt(j,kk)) * &
                exp(c3les*(pt(j,kk)-tmelt)*zl)+(1.-foealfa(pt(j,kk))) * &
                exp(c3ies*(pt(j,kk)-tmelt)*zi))
              zqsat = zqsat*zqp
              zqsat = min(0.5,zqsat)
              zcor = 1. - vtmpc1*zqsat
              zf = foealfa(pt(j,kk))*r5alvcp*zl**2 + &
                   (1.-foealfa(pt(j,kk)))*r5alscp*zi**2
              zcond1 = (pq(j,kk)*zcor**2-zqsat*zcor)/(zcor**2+zqsat*zf)
              if ( abs(zcond) < 1.e-20 ) zcond1 = 0.
              pt(j,kk) = pt(j,kk) + foeldcpm(pt(j,kk),alv,als,rcpd)*zcond1
              pq(j,kk) = pq(j,kk) - zcond1
            end if
          end if
        end do
      elseif ( kcall == 0 ) then
        do j = its,ite
          zqp = 1./psp(j)
          zqsat = foeewm(pt(j,kk),rv,rd)*zqp
          zqsat = min(0.5,zqsat)
          zcor = 1./(1.-vtmpc1*zqsat)
          zqsat = zqsat*zcor
          zcond1 = (pq(j,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(j,kk),alv,als,rcpd))
          pt(j,kk) = pt(j,kk) + foeldcpm(pt(j,kk),alv,als,rcpd)*zcond1
          pq(j,kk) = pq(j,kk) - zcond1
!added
          zqsat = foeewm(pt(j,kk),rv,rd)*zqp
          zqsat = min(0.5,zqsat)
          zcor = 1./(1.-vtmpc1*zqsat)
          zqsat = zqsat*zcor
          zcond1 = (pq(j,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(j,kk),alv,als,rcpd))
          pt(j,kk) = pt(j,kk) + foeldcpm(pt(j,kk),alv,als,rcpd)*zcond1

          pq(j,kk) = pq(j,kk) - zcond1
        end do
      end if

      return
      end subroutine cuadjtqn

!-------------------------------------------------------------------------------
   REAL FUNCTION fpvs(t,ice,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c)
!-------------------------------------------------------------------------------
   IMPLICIT NONE
!-------------------------------------------------------------------------------
   REAL :: t,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c,dldt,xa,xb,dldti,         &
           xai,xbi,ttp,tr
   INTEGER :: ice
!
   ttp=t0c+0.01
   dldt=cvap-cliq
   xa=-dldt/rv
   xb=xa+hvap/(rv*ttp)
   dldti=cvap-cice
   xai=-dldti/rv
   xbi=xai+hsub/(rv*ttp)
   tr=ttp/t
   if(t.lt.ttp.and.ice.eq.1) then
     fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
   else
     fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
   endif
!
   if (t.lt.180.) then
     tr=ttp/180.
     if(t.lt.ttp.and.ice.eq.1) then
       fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
     else
       fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
     endif
   endif
!
   if (t.ge.330.) then
     tr=ttp/330
     if(t.lt.ttp.and.ice.eq.1) then
       fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
     else
       fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
     endif
   endif
!
   END FUNCTION fpvs
!-------------------------------------------------------------------------------
!
!-------------------------------------------------------------------------------
   subroutine nsasinit(rthcuten,rqvcuten,rqccuten,rqicuten,                    &
                      rucuten,rvcuten,                                         &  
                      restart,p_qc,p_qi,p_first_scalar,                        &
                      allowed_to_read,                                         &
                      ids, ide, jds, jde, kds, kde,                            &
                      ims, ime, jms, jme, kms, kme,                            &
                      its, ite, jts, jte, kts, kte                  )
!-------------------------------------------------------------------------------
   implicit none
!-------------------------------------------------------------------------------
   logical , intent(in)           ::  allowed_to_read,restart
   integer , intent(in)           ::  ids, ide, jds, jde, kds, kde,            &
                                      ims, ime, jms, jme, kms, kme,            &
                                      its, ite, jts, jte, kts, kte
   integer , intent(in)           ::  p_first_scalar, p_qi, p_qc
   real,     dimension( ims:ime , kms:kme , jms:jme ) , intent(out) ::         &
                                                              rthcuten,        &
                                                              rqvcuten,        &
                                                               rucuten,        &
                                                               rvcuten,        &
                                                              rqccuten,        &
                                                              rqicuten
   integer :: i, j, k, itf, jtf, ktf
!
   jtf=min0(jte,jde-1)
   ktf=min0(kte,kde-1)
   itf=min0(ite,ide-1)
!
   if(.not.restart)then
     do j = jts,jtf
       do k = kts,ktf
         do i = its,itf
           rthcuten(i,k,j)=0.
           rqvcuten(i,k,j)=0.
           rucuten(i,k,j)=0.   
           rvcuten(i,k,j)=0.   
         enddo
       enddo
     enddo
!
     if (p_qc .ge. p_first_scalar) then
       do j = jts,jtf
         do k = kts,ktf
           do i = its,itf
             rqccuten(i,k,j)=0.
           enddo
         enddo
       enddo
     endif
!
     if (p_qi .ge. p_first_scalar) then
       do j = jts,jtf
         do k = kts,ktf
           do i = its,itf
             rqicuten(i,k,j)=0.
           enddo
         enddo
       enddo
     endif
   endif
!
   end subroutine nsasinit
!-------------------------------------------------------------------------------
!
! add external functions
  !------------------------------------------------------
      real function foealfa(tt)
  !     foealfa is calculated to distinguish the three cases:
  !
  !                       foealfa=1            water phase
  !                       foealfa=0            ice phase
  !                       0 < foealfa < 1      mixed phase
  !
  !               input : tt = temperature
  !
        implicit none
        real tt
        real rtwat, rtice

        rtwat=273.16
        rtice=273.16-23.
         foealfa = min(1.,((max(rtice,min(rtwat,tt))-rtice) &
     &  /(rtwat-rtice))**2)
  !
        return
      end function foealfa

      real function foeewm(tt,rv,rd)
        implicit none
        real tt, rv, rd
        real tmelt, c2es, c3les, c3ies, c4les, c4ies

        tmelt=273.16
        c2es=610.78*rd/rv
        c3les=17.2693882
        c3ies=21.875
        c4les=35.86
        c4ies=7.66
        foeewm  = c2es * &
     &     (foealfa(tt)*exp(c3les*(tt-tmelt)/(tt-c4les))+ &
     &     (1.-foealfa(tt))*exp(c3ies*(tt-tmelt)/(tt-c4ies)))
      return
      end function foeewm
  !      
      real function foedem(tt, alv, als, rcpd)
        implicit none
        real tt, alv, als, rcpd
        real tmelt, c3les, c3ies, c4les, c4ies, c5les, c5ies, r5alvcp, r5alscp

        tmelt=273.16
        c3les=17.2693882
        c3ies=21.875
        c4les=35.86
        c4ies=7.66
        c5les=c3les*(tmelt-c4les)
        c5ies=c3ies*(tmelt-c4ies)
        r5alvcp=c5les*alv*rcpd
        r5alscp=c5ies*als*rcpd

        foedem  = foealfa(tt)*r5alvcp*(1./(tt-c4les)**2)+ &
     &              (1.-foealfa(tt))*r5alscp*(1./(tt-c4ies)**2)
      return
      end function foedem
  !
      real function foeldcpm(tt,alv,als,rcpd)
        implicit none
        real tt,alv,als,rcpd
        real ralvdcp, ralsdcp

        ralvdcp=alv*rcpd
        ralsdcp=als*rcpd

        foeldcpm = foealfa(tt)*ralvdcp+ &
     &        (1.-foealfa(tt))*ralsdcp
      return
      end function  foeldcpm
!------------------------------------------------------
END MODULE module_cu_ksas
!
