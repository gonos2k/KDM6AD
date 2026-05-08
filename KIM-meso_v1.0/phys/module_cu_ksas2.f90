



MODULE module_cu_ksas2
CONTAINS

   subroutine cu_ksas2(dt,dx,p3di,p3d,pi3d,qc3d,qi3d,rho3d,itimestep,stepcu,    &
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

   implicit none



































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

   real,     dimension( ims:ime, jms:jme )                                    ,&
             intent(in   ) ::                                            xland

   real,     dimension( ims:ime, kms:kme, jms:jme )                           ,&
              intent(in   )   ::                                           u3d,&
                                                                           v3d
   logical,  dimension( ims:ime, jms:jme )                                    ,&
             intent(inout) ::                                      cu_act_flag

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

   integer ::  im,kx,kx1



   if (mp_physics .eq. 0) then
     ncloud = 0
   elseif ( mp_physics .eq. 1 .or. mp_physics .eq. 3 ) then
     ncloud = 1
   else
     ncloud = 2
   endif

   if(present(pgcon)) then
     pgcon_use = pgcon
   else

     pgcon_use  = 0.55    
     
     
   endif

   do j = jts,jte
     do i = its,ite
       cu_act_flag(i,j)=.TRUE.
     enddo
   enddo

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



   do j = jts,jte
     do k = kts,kte
       kp = k+1
       do i = its,ite
         dot(i,k) = -5.0e-4*g*rho3d(i,k,j)*(w(i,k,j)+w(i,kp,j))
         prsll(i,k)=p3d(i,k,j)  
         prsii(i,k)=p3di(i,k,j) 
       enddo
     enddo

     do i = its,ite
       prsii(i,kte+1)=p3di(i,kte+1,j) 
     enddo

     do i = its,ite
       zii(i,1)=0.0
     enddo     

     do k = kts,kte                                            
       do i = its,ite
         zii(i,k+1)=zii(i,k)+dz8w(i,k,j)
       enddo
     enddo

     do k = kts,kte                
       do i = its,ite                                                  
         zll(i,k)=0.5*(zii(i,k)+zii(i,k+1))
       enddo                                                         
     enddo

     do k = kts,kte
       do i = its,ite
         del(i,k)=prsll(i,k)*g/r_d*dz8w(i,k,j)/t3d(i,k,j)*0.001 
         u1(i,k)=u3d(i,k,j)
         v1(i,k)=v3d(i,k,j)
         q1(i,k)=qv3d(i,k,j)

         t1(i,k)=t3d(i,k,j)
         qi2(i,k) = qi3d(i,k,j)
         qc2(i,k) = qc3d(i,k,j)
       enddo
     enddo



     call nsas22d(delt=delt,delx=dx,del=del(its,kts),                           &
              prsl=prsll(its,kts),prsi=prsii(its,kts),prslk=pi3d(ims,kms,j),   &
              zl=zll(its,kts), zi=zii(its,kts),                                & 
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
              lq=im, km=kx, km1=kx1,                                           & 
              ids=ids,ide=ide, jds=jds,jde=jde, kds=kds,kde=kde,               &
              ims=ims,ime=ime, jms=jms,jme=jme, kms=kms,kme=kme,               &
              its=its,ite=ite, jts=jts,jte=jte, kts=kts,kte=kte   )

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

     IF(PRESENT(rthcuten).AND.PRESENT(rqvcuten)) THEN
       
       do k = kts,kmax 
         do i = its,ite
           rthcuten(i,k,j)=(t1(i,k)-t3d(i,k,j))/pi3d(i,k,j)*rdelt
           rqvcuten(i,k,j)=(q1(i,k)-qv3d(i,k,j))*rdelt
         enddo
       enddo
     ENDIF

     IF(PRESENT(rucuten).AND.PRESENT(rvcuten)) THEN
       
       do k = kts,kmax 
         do i = its,ite
           rucuten(i,k,j)=(u1(i,k)-u3d(i,k,j))*rdelt
           rvcuten(i,k,j)=(v1(i,k)-v3d(i,k,j))*rdelt
         enddo
       enddo
     ENDIF

     IF(PRESENT( rqicuten )) THEN
       IF ( F_QI ) THEN
         
         do k = kts,kmax 
           do i = its,ite
             rqicuten(i,k,j)=(qi2(i,k)-qi3d(i,k,j))*rdelt
           enddo
         enddo
       ENDIF
     ENDIF

     IF(PRESENT( rqccuten )) THEN
       IF ( F_QC ) THEN
         
         do k = kts,kmax 
           do i = its,ite
             rqccuten(i,k,j)=(qc2(i,k)-qc3d(i,k,j))*rdelt
           enddo
         enddo
       ENDIF
     ENDIF

   enddo 

   return
   end subroutine cu_ksas2




   subroutine nsas22d(delt,delx,del,prsl,prsi,prslk,zl,zi,                      & 
            ncloud,                                                            &
            qc2,qi2,                                                           &
            q1,t1,rain,kbot,ktop,                                              &
            icps,                                                              &
            lat,slimsk,dot,u1,v1,cp_,cliq_,cvap_,g_,hvap_,rd_,rv_,fv_,ep2,     &
            cice,xls,psat,                                                     &
            dx_factor_nsas,                                                    &
            hpbl,hpbl_hold,                                                    &
            kbmax,kbm,kmax,                                                    &
            lq,km,km1,                                                         & 
            ids,ide, jds,jde, kds,kde,                                         &
            ims,ime, jms,jme, kms,kme,                                         &
            its,ite, jts,jte, kts,kte)




































































































   implicit none




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



   real            ::  cp_,cliq_,cvap_,g_,hvap_,rd_,rv_,fv_,ep2
   real            ::  pi_,qmin_,t0c_,cice,xlv0,xls,psat
   integer         ::  dx_factor_nsas
   integer         ::  lat,                                                    &
                       ncloud,                                                 &
                       lq,km,km1,                                              & 
                       ids,ide, jds,jde, kds,kde,                              &
                       ims,ime, jms,jme, kms,kme,                              &
                       its,ite, jts,jte, kts,kte

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

   real            ::  rain(its:ite)
   real            ::  hpbl(ims:ime),hpbl_hold(ims:ime)
   integer         ::  kbot(its:ite),ktop(its:ite),icps(its:ite)
   real            ::  slimsk(ims:ime)



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



   real            ::  po1(its:ite,kts:kte),wu2(its:ite,kts:kte),              &
                       buo(its:ite,kts:kte),drag(its:ite,kts:kte)
   real            ::  wbar(its:ite),wc(its:ite),clear(its:ite)

   real            ::  sigma, sigma_con
   real            ::  mbdt
   real            ::  dtconv(its:ite)
   real            ::  deltv(its:ite),acrt(its:ite)
   real            ::  apbl(its:ite),dtpbl(its:ite)
   real            ::  qeso(its:ite,kts:kte)
   real            ::  tvo(its:ite,kts:kte),dbyo(its:ite,kts:kte)
   real            ::  heo(its:ite,kts:kte),heso(its:ite,kts:kte),kb_heo(its:ite) 
   real            ::  qrcd(its:ite,kts:kte)
   real            ::  dellah(its:ite,kts:kte),dellaq(its:ite,kts:kte)

   integer         ::  kb(its:ite),kbcon(its:ite)
   integer         ::  kbcon1(its:ite)
   real            ::  hmax(its:ite),delq(its:ite)
   real            ::  hkbo(its:ite),qkbo(its:ite)
   integer         ::  lmin(its:ite),jmin(its:ite)
   integer         ::  ktcon(its:ite)
   integer         ::  ktcon1(its:ite)
   integer         ::  n_kb(its:ite), n_kbcon1(its:ite), n_ktcon(its:ite) 
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

   logical         ::  totflg, cnvflg(its:ite),flg(its:ite)
   logical         ::  n_cnvflg(its:ite) 
   real            ::  pgcon(its:ite,kts:kte)





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
   sigma_con = tan(0.4*pi_)/(dx5km-dx1km)                     
   sigma  = (1.-1./pi_*(atan(sigma_con*(delx-dx5km))+pi_/2.)) 

   if (delx.lt.dx5km) then
     sigma = min(sigma - 0.01684 * delx/1000. + 0.0842, 1.0)
   endif

   cinpcr = (cinpcrmn + 0.5*(cinpcrmx-cinpcrmn)) * (1.-sigma)



   do i = its,ite
     rain(i)    = 0.0
     kbot(i)    = kte+1
     ktop(i)    = 0
     icps(i)    = 0
     cnvflg(i)  = .false. 
     kb_heo(i)  = 0.0     
     n_kbcon1(i)= 0       
     n_ktcon(i) = 0       
     n_kb(i)    = 0       
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




   kmax = min(kmax,kte)
   kmax1 = kmax - 1
   kbm = min(kbm,kte)



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

   do k = kts,kmax
     do i = its,ite

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










  call trigger_ntdk &
  &     (its=its, ite=ite, kts=kts, kte=kmax, & 
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

     enddo
   enddo



   do k = kts,kmax
     do i = its,ite
       heo(i,k)  = g_ * zl(i,k) + cp_* to(i,k) + hvap_ * qo(i,k)
       heso(i,k) = g_ * zl(i,k) + cp_* to(i,k) + hvap_ * qeso(i,k)
     enddo
   enddo




   do i = its,ite
     kb(i) = 1
     if (cnvflg(i)) then
       kb(i) = n_kb(i)
     endif
   enddo





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



   do i = its,ite
     if(cnvflg(i)) then
       indx = kb(i)
       hkbo(i) = kb_heo(i)
       qkbo(i) = qo(i,indx)
     endif
   enddo

   do i = its,ite
     flg(i) = cnvflg(i)
     kbcon(i) = kmax
   enddo

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

   do i = its,ite
     if(kbcon(i).eq.kmax) cnvflg(i) = .false.
   enddo

   do k = kts1,kte
     do i = its,ite
       zi(i,k) = 0.5*(zl(i,k-1)+zl(i,k))
     enddo
   enddo

   do k = kts,kte1
     do i = its,ite
       xlamb(i,k) = clam / zi(i,k+1) 
     enddo
   enddo




   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.gt.kbcon(i))) then
         xlamb(i,k) = xlamb(i,kbcon(i))
       endif
     enddo
   enddo




   do i = its,ite
     if(cnvflg(i)) then
       xlamud(i) = xlamb(i,kbcon(i))
     endif
   enddo




   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.gt.kbcon(i))) then
         tem = qeso(i,k)/qeso(i,kbcon(i))
         fent1(i,k) = tem**2
         fent2(i,k) = tem**3
       endif
     enddo
   enddo





   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.(k.ge.kbcon(i))) then
          tem = cxlamu * frh(i,k) * fent2(i,k)
          xlamb(i,k) = xlamb(i,k)*fent1(i,k) + tem
       endif
     enddo
   enddo



   do k = kts,kte
     do i = its,ite
      if(cnvflg(i)) then
         eta(i,k) = 1.
       endif
     enddo
   enddo

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


   do i = its,ite
     ktcon(i) = 1
     if (cnvflg(i)) then
       ktcon(i) = n_ktcon(i)
     endif
   enddo

   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return



   do i = its,ite 
     if(cnvflg(i)) then
       hmin(i) = heo(i,kbcon1(i))
       lmin(i) = kbmax
       jmin(i) = kbmax
    endif
   enddo

   do k = kts1,kbmax 
     do i = its,ite 
       if(cnvflg(i).and.k.gt.kbcon1(i).and.heo(i,k).lt.hmin(i)) then
         lmin(i) = k + 1
         hmin(i) = heo(i,k)
       endif
     enddo
   enddo



   do i = its,ite
     if(cnvflg(i)) then
       jmin(i) = min(lmin(i),ktcon(i)-1)
       jmin(i) = max(jmin(i),kbcon1(i)+1)
       if(jmin(i).ge.ktcon(i)) cnvflg(i) = .false.
       if(jmin(i).le.kbcon(i)) cnvflg(i) = .false.
     endif
   enddo



   do i = its,ite
     if(cnvflg(i)) then
       k = kbcon(i)
       dp = 1000. * del(i,k)
       xmbmax(i) = dp / (g_ * dt2)
     endif
   enddo



   do k = kts1,kmax
     do i = its,ite
       if (cnvflg(i).and.k.gt.kb(i)) then
         alpha1 = min((-0.7*log(100.)+24.)*0.0001,c0)
         beta1 = 0.07

         if (to(i,k).gt.t0c_) then
           c0fac = alpha1
         else
           c0fac = alpha1*exp(beta1*(to(i,k)-t0c_))
         endif

         c0fac = max(0.0,c0fac)
         c0t(i,k) = c0fac
       endif

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



   do i = its,ite
     if (cnvflg(i)) then
       aa1(i) = 0.
     endif
   enddo

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

   do i = its,ite
     if(cnvflg(i).and.aa1(i).le.0.) cnvflg(i) = .false.
   enddo

   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return





   do i = its,ite
     if (cnvflg(i)) then
       aa2(i) = aafac * aa1(i)
     endif
   enddo

   do i = its,ite
     flg(i) = cnvflg(i)
     ktcon1(i) = kmax1
   enddo

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



   bb1 = 2. * (1.+bet1*cd1)
   bb2 = 2. / (f1*(1.+gam1))




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



   wc = 0. ; wbar = 0. ; sumx = 0.

   ptem = -0.5 * rd_ / g_
   do k = kts1,kmax
     do i = its,ite
       po1(i,k) = .5 * (p(i,k) + p(i,k+1))
     enddo
   enddo

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





   do i = its,ite
     if (cnvflg(i)) then
       tem = wbar(i) / wc(i)
       tem = max(tem, 0.)
       clear(i) = 1. - tem
       clear(i) = max(min(clear(i), 1.0), 0.)
       if (wbar(i).gt.0. .and. wbar(i).gt.wc(i)) cnvflg(i) = .false.
     endif
   enddo



   do i = its,ite
     if(cnvflg(i)) then
       kk = ktcon(i)
       ktcon(i) = ktcon1(i)
       ktcon1(i) = kk
     endif
   enddo

   do i = its,ite
     if (ktcon(i).le.kb(i)) cnvflg(i) = .false.
   enddo

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



   if (ncloud.gt.0) then



     do i = its,ite
       if(cnvflg(i)) then
         k = ktcon(i)-1
         gamma = el2orc * qeso(i,k) / (to(i,k)**2)
         qrch = qeso(i,k)                                                      &
                + gamma * dbyo(i,k) / (hvap_ * (1. + gamma))
         dq = qcko(i,k) - qrch



         if(dq.gt.0.) then
           qlko_ktcon(i) = dq * sigma
           qcko(i,k) = qrch + dq * (1.-sigma)
         endif
       endif
     enddo
   endif





   do i = its,ite
     if(cnvflg(i)) then
       vshear(i) = 0.
     endif
   enddo

   do k = kts1,kmax
     do i = its,ite
       if(k.gt.kb(i).and.k.le.ktcon(i).and.cnvflg(i)) then
         shear= sqrt((uo(i,k)-uo(i,k-1)) ** 2                                  &
                   + (vo(i,k)-vo(i,k-1)) ** 2)
         vshear(i) = vshear(i) + shear
       endif
     enddo
   enddo

   do i = its,ite
     if(cnvflg(i)) then
       vshear(i) = 1.e3 * vshear(i) / (zi(i,ktcon(i)+1)-zi(i,kb(i)+1))
       e1 = 1.591-.639*vshear(i)                                               &
           +.0953*(vshear(i)**2)-.00496*(vshear(i)**3)
       edt(i)  = 1.-e1

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



   do i = its,ite
     if(cnvflg(i)) then
       sumx(i) = 0.
     endif
   enddo

   do k = kts,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.ge.1.and.k.lt.kbcon(i)) then
         dz = zi(i,k+2) - zi(i,k+1)
         sumx(i) = sumx(i) + dz
       endif
     enddo
   enddo

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



   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i)) then
         etad(i,k) = 1.
       endif
       qrcdo(i,k) = 0.
       qrcd(i,k) = 0.
     enddo
   enddo

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



   do i = its,ite
     if(cnvflg(i)) then
      pwevo(i) = 0.
     endif
   enddo

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

   do i = its,ite
     if(cnvflg(i).and.aa1(i).le.0.) cnvflg(i) = .false.
   enddo

   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return




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

         dellah(i,k) = dellah(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1               &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3               &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2*dz              &
         +  aup*tem1*eta(i,k-1)*.5*(hcko(i,k)+hcko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(hcdo(i,k)+hcdo(i,k-1))*dz) *g_/dp

         dellaq(i,k) = dellaq(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1q              &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3q              &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2q*dz             &
         +  aup*tem1*eta(i,k-1)*.5*(qcko(i,k)+qcko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(qrcdo(i,k)+qrcdo(i,k-1))*dz) *g_/dp

         dellau(i,k) = dellau(i,k) +                                           &
             ((aup * eta(i,k) - adw * edto(i) * etad(i,k)) * dv1u              &
         - (aup * eta(i,k-1) - adw * edto(i) * etad(i,k-1))* dv3u              &
         - (aup*tem*eta(i,k-1)+adw*edto(i)*ptem*etad(i,k))*dv2u*dz             &
         +  aup*tem1*eta(i,k-1)*.5*(ucko(i,k)+ucko(i,k-1))*dz                  &
         +  adw*edto(i)*ptem1*etad(i,k)*.5*(ucdo(i,k)+ucdo(i,k-1))*dz          &
         - pgcon(i,k)*(aup*eta(i,k-1)-adw*edto(i)*etad(i,k))*(dv1u-dv3u))*g_/dp

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



       dellal(i,indx) = eta(i,indx-1) * qlko_ktcon(i) * g_ / dp
     endif
   enddo



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













   do k = kts,kmax
     do i = its,ite
       if(cnvflg(i)) then
         qeso(i,k)=0.01* fpvs(to(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k) / (p(i,k) + (eps-1.) * qeso(i,k))
         qeso(i,k) = max(qeso(i,k),qmin_)

       endif
     enddo
   enddo



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

   k = kmax
   do i = its,ite
     if(cnvflg(i)) then
       heo(i,k)  = g_ * zl(i,k) + cp_ * to(i,k) + hvap_ * qo(i,k)
       heso(i,k) = g_ * zl(i,k) + cp_ * to(i,k) + hvap_ * qeso(i,k)
     endif
   enddo

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

   do k = kts1,kmax1
     do i = its,ite
       if(cnvflg(i).and.k.gt.kb(i).and.k.lt.ktcon(i)) then
         alpha1 = min((-0.7*log(100.)+24.)*0.0001,c0)
         beta1 = 0.07

         if (to(i,k).gt.t0c_) then
           c0fac = alpha1
         else
           c0fac = alpha1*exp(beta1*(to(i,k)-t0c_))
         endif

         c0fac = max(0.0,c0fac)
         c0t(i,k) = c0fac

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





   do i = its,ite
     xpwev(i) = 0.
   enddo

   do i = its,ite
     if(cnvflg(i)) then
       jmn = jmin(i)
       xhcd(i,jmn) = heo(i,jmn)
       xqcd(i,jmn) = qo(i,jmn)
       qrcd(i,jmn) = qeso(i,jmn)
     endif
   enddo

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



   do i = its,ite
     tem = zi(i,ktcon1(i)) - zi(i,kbcon1(i))
     dtconv(i) = tfac * tem / wc(i)
     dtconv(i) = max(dtconv(i),dtmin)
     dtconv(i) = min(dtconv(i),dtmax)

   enddo





   do i = its,ite
     if (cnvflg(i).and.slimsk(i).eq.2.) then
       wc(i) = 0.
       sumx(i) = 0.
     endif
   enddo

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

   do i = its,ite
     if (cnvflg(i).and.slimsk(i).eq.2.) then
       wc(i) = wc(i) / sumx(i)
       dtpbl(i) = zl(i,kbcon(i))/wc(i)
     else
       dtpbl(i) = dtconv(i)
     endif
   enddo

   do i = its,ite
     if (cnvflg(i)) then
       apbl(i) = g_ * (hpbl(i)-hpbl_hold(i))/dt2 * dtpbl(i)
       apbl(i) = min(max(apbl(i),0.0),aa1(i))
     endif
   enddo

   do i = its,ite
     if(cnvflg(i)) then
       f(i) = (aa1(i) - apbl(i)) / dtconv(i)
       if(f(i).le.0.) cnvflg(i) = .false.
     endif
     if(cnvflg(i)) then
       xk(i) = (xaa0(i) - aa1(i)) / mbdt
       if(xk(i).ge.0.) cnvflg(i) = .false.
     endif



     if(cnvflg(i)) then
       xmb(i) = -f(i) / xk(i)
       xmb(i) = xmb(i) * clear(i) * (1.-sigma)
       xmb(i) = min(xmb(i),xmbmax(i))
     endif
     pden(i) = p(i,kbcon(i))/to(i,kbcon(i))/rd_
     pdot(i) = 10.* dot(i,kbcon(i))

     if (xmb(i).lt.pdot(i)/g_) cnvflg(i) = .false.
   enddo
   totflg = .true.
   do i = its,ite
     totflg = totflg .and. (.not. cnvflg(i))
   enddo
   if(totflg) return



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





   do i = its,ite
     delhbar(i) = 0.
     delqbar(i) = 0.
     deltbar(i) = 0.
     qcond(i) = 0.
     delubar(i) = 0.
     delvbar(i) = 0.
   enddo

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

   do k = kts,kmax 
     do i = its,ite 
       if (cnvflg(i) .and. k.le.ktcon(i)) then
         qeso(i,k)=0.01* fpvs(t1(i,k),1,rd_,rv_,cvap_,cliq_,cice,xlv0,xls,psat,t0c_)
         qeso(i,k) = eps * qeso(i,k)/(p(i,k) + (eps-1.)*qeso(i,k))
         qeso(i,k) = max(qeso(i,k), qmin_)
       endif
     enddo
   enddo

   do i = its,ite 
     rntot(i) = 0.
     delqev(i) = 0.
     delq2(i) = 0.
     flg(i) = cnvflg(i) 
   enddo



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

       if (cnvflg(i).and.k.lt.ktcon(i)) then
         dp = del(i,k)
         qrs(i,k) = max(qrsk(i,k)*g_/dp*xmb(i)*dt2 - max(qevap(i),0.),0.)
         qci(i,k) = max(qcirs(i,k) - aup*pwo(i,k),0.) * g_/dp*xmb(i)*dt2


       endif
     enddo
   enddo



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



   if (ncloud.gt.0) then
     do k = kts,kmax 
       do i = its,ite 
         if (cnvflg(i) .and. rain(i).gt.0.) then
           if (k.ge.kbcon(i).and.k.le.ktcon(i)) then
             tem  = dellal(i,k) * xmb(i) * dt2
             tem1 = max(0.0, min(1.0, (tcr-t1(i,k))*tcrf))
             if (ncloud.ge.2) then
               qi2(i,k) = qi2(i,k) + tem * tem1            
               qc2(i,k) = qc2(i,k) + tem *(1.0-tem1)       
             else
               qc2(i,k) = qc2(i,k) + tem
             endif
           endif
         endif
       enddo
     enddo
   endif

   end subroutine nsas22d



 subroutine trigger_ntdk( its, ite, kts, kte, rpten, rpren, rpgeo, rpaph, rpgeoh,& 
                         rpap,& 
     &      cpd, rd, rv, alv, als,g,& 
     &      kb_heo, cubot, cutop, kdpl, ldcum) 
      implicit none

      real     cpd, rd, rv, alv, als, g, alf


      integer  klon, klev, klevp1, klevm1
      integer  its, ite, kts, kte 
      real     rpten(its:ite,kts:kte),        rpren(its:ite,kts:kte),&
     &         rpgeo(its:ite,kts:kte)
      real     rpaph(its:ite,kts:kte+1), rpgeoh(its:ite,kts:kte+1)


      real     rpap(its:ite,kts:kte)


      integer  nk,is,ikb,ikt,levels
      integer  kctop(its:ite),kcbot(its:ite)
      integer  zcbase(its:ite), itoppacel(its:ite)
      integer  klab(its:ite,kts:kte)


      real     ptu(its:ite,kts:kte), pqu(its:ite,kts:kte), dhen(its:ite,kts:kte), dh(its:ite,kts:kte),&
     &         kup(its:ite,kts:kte), vptu(its:ite,kts:kte), vten(its:ite,kts:kte), zbuo(its:ite,kts:kte), abuoy(its:ite,kts:kte)

      real     plu(its:ite,kts:kte) 
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



      integer  cubot(its:ite), cutop(its:ite), kdpl(its:ite)
      real     kb_heo(its:ite) 
      logical  ldcum(its:ite)


      klev   = kte - kts + 1 
      klevp1 = klev + 1      
      klevm1 = klev - 1      

      do j=its,ite
         cutop(j)     = 0 
         cubot(j)     = 0 
         kctop(j)     = 0
         kcbot(j)     = 0
         kdpl(j)      = klev     
         wbase(j)     = 0.       
         ldcum(j)     = .false.  
         kb_heo(j)    = 0. 
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
      
      
      

      
      
      
      
      do k=kts,kte
        
        zz = klev - (k - 1)
        do j=its,ite
          pten(j,zz) = rpten(j,k)
          pgeo(j,zz) = rpgeo(j,k)
          pren(j,zz) = rpren(j,k)
          pap(j,zz)  = rpap(j,k)
        enddo
        
      enddo

      
      do k=kts,kte+1
        
        zz = klevp1 - (k - 1)
        do j=its,ite
          pgeoh(j,zz) = rpgeoh(j,k)
          paph(j,zz)  = rpaph(j,k)
        enddo
        
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
      
      
      


      

      
      
      
      
      
      deltt = 0.2
      deltq = 1.0e-4
      do j=its,ite
        deepflag(j) = .false.
      end do 

      do k=kte,kts,-1
        do j=its,ite
          if((paph(j,klev+1)-paph(j,k)) .lt. 350.e2) itoppacel(j) = k
        end do
      end do 

      do levels=klevm1-1,klev/2+1,-1 
        do k=kts,kte
          do j=its,ite
            plu(j,k)   = 0.0  
            ptu(j,k)   = 0.0  
            pqu(j,k)   = 0.0  
            dh(j,k)    = 0.0  
            dhen(j,k)  = 0.0  
            kup(j,k)   = 0.0  
            vptu(j,k)  = 0.0  
            vten(j,k)  = 0.0  
            abuoy(j,k) = 0.0
            zbuo(j,k)  = 0.0
            klab(j,k)  = 0
          end do
        end do 

        do j=its,ite
          kcbot(j)     = levels
          kctop(j)     = levels
          zqold(j)     = 0.
          lldcum(j)    = .false.
          resetflag(j) = .false.
          loflag(j)    = (.not. deepflag(j)) .and. (levels.ge.itoppacel(j))
        end do 

        
        do k=levels,2,-1 
          is=0
          do j=its,ite
            if(loflag(j))then
              is=is+1
            endif
          enddo
          if(is.eq.0) exit 

          
          if(k .eq. levels) then
            do j=its,ite
              if(loflag(j)) then
                if((paph(j,klev+1)-paph(j,k)) < 60.e2) then 
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
                pqu(j,k+1)  = qmix + deltq 
                dhen(j,k+1) = zmix + tmix*cpd
                dh(j,k+1)   = dhen(j,k+1) + deltt*cpd 
                ptu(j,k+1)  = (dh(j,k+1)-pgeoh(j,k+1))*rcpd
                kup(j,k+1)  = 0.5
                klab(j,k+1) = 1
                vptu(j,k+1) = ptu(j,k+1)*(1.+vtmpc1*pqu(j,k+1))
                vten(j,k+1) = ptenh(j,k+1)*(1.+vtmpc1*pqenh(j,k+1))
                zbuo(j,k+1) = (vptu(j,k+1)-vten(j,k+1))/vten(j,k+1)
                kb_heo(j) = dh(j,k+1) + alv * pqu(j,k+1) 
              end if
            end do
          end if

          
          do j=its,ite
            if(loflag(j)) then
              fscale    = min(1.,(pqsen(j,k)/pqsen(j,levels))**3)
              eta(j)    = 1.75e-3*fscale  
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
          end do 

          
          ik=k
          icall=1
          call cuadjtqn(its,ite,kts,kte,ik,zph,ptu,pqu,loflag,icall,rv,rd,alv,als,rcpd)
          do j=its,ite
            if( loflag(j) ) then
              zdq        = max((zqold(j) - pqu(j,k)),0.) 

              plu(j,k)   = plu(j,k+1) + zdq 
              zlglac     = zdq*((1.-foealfa(ptu(j,k))) - &
                          (1.-foealfa(ptu(j,k+1))))
              plu(j,k)   = 0.5*plu(j,k)     

              dh(j,k)    = pgeoh(j,k) + cpd*(ptu(j,k)+ralfdcp*zlglac) 
              
              vptu(j,k)  = ptu(j,k)*(1.+vtmpc1*pqu(j,k)-plu(j,k))+&
                          ralfdcp*zlglac
              vten(j,k)  = ptenh(j,k)*(1.+vtmpc1*pqenh(j,k))
              zbuo(j,k)  = (vptu(j,k) - vten(j,k))/vten(j,k) 
              abuoy(j,k) = (zbuo(j,k)+zbuo(j,k+1))*0.5*g
              atop1      = 1.0 - 2.*coef(j)
              atop2      = 2.0*dz(j)*abuoy(j,k)
              abot       = 1.0 + 2.*coef(j)
              kup(j,k)   = (atop1*kup(j,k+1) + atop2) / abot 

              if ( plu(j,k) > 0. .and. klab(j,k+1) == 1 ) then 
                ik        = k + 1
                zqsu      = foeewm(ptu(j,ik),rv,rd)/paph(j,ik)
                zqsu      = min(0.5,zqsu)
                zcor      = 1./(1.-vtmpc1*zqsu)
                zqsu      = zqsu*zcor 
                zdq       = min(0.,pqu(j,ik)-zqsu)
                zalfaw    = foealfa(ptu(j,ik))
                zfacw     = c5les/((ptu(j,ik)-c4les)**2)
                zfaci     = c5ies/((ptu(j,ik)-c4ies)**2)
                zfac      = zalfaw*zfacw + (1.-zalfaw)*zfaci
                zesdp     = foeewm(ptu(j,ik),rv,rd)/paph(j,ik)
                zcor      = 1./(1.-vtmpc1*zesdp)
                zdqsdt    = zfac*zcor*zqsu
                zdtdp     = rd*ptu(j,ik)/(cpd*paph(j,ik))
                zdp       = zdq/(zdqsdt*zdtdp) 
                zcbase(j) = paph(j,ik) + zdp 
                
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

              if(kup(j,k) .lt. 0.)then 
                loflag(j) = .false.
                if(plu(j,k+1) .gt. 0.) then 
                  kctop(j) = k
                  lldcum(j) = .true.
                else
                  lldcum(j) = .false.
                end if
              else
                if(plu(j,k) .gt. 0.)then
                  klab(j,k)=2 
                else
                  klab(j,k)=1
                end if
              end if
            end if
          end do
        end do 
       
        needreset = .false.
        do j=its,ite
          ikb = kcbot(j)
          ikt = kctop(j)
          if(paph(j,ikb) - paph(j,ikt) < zdnoprc) lldcum(j) = .false.
          if(lldcum(j)) then
            ldcum(j)     = .true.
            deepflag(j)  = .true.
            wbase(j)     = sqrt(max(2.*kup(j,ikb),0.)) 
            needreset    = .true.
            resetflag(j) = .true.
            cubot(j)     = ikb
            cutop(j)     = ikt
            kdpl(j)      = levels+1
          end if
        end do
      end do 

      do j=its,ite
        cubot(j) = klevp1 - cubot(j)
        cutop(j) = klevp1 - cutop(j)
        kdpl(j)  = klevp1 - kdpl(j)
         print*, j,ldcum(j),cubot(j),cutop(j),kdpl(j),kb_heo(j),klevp1
      end do

      
      
      
      





      end subroutine trigger_ntdk

     subroutine cuadjtqn                 &
     &    (its,ite,kts,kte, kk, psp, pt, pq, ldflag, kcall, rv,rd,alv,als,rcpd)









































      implicit none

      integer  klev,klon
      integer  its,ite,kts,kte 

      real     pt(its:ite,kts:kte),          pq(its:ite,kts:kte),  &
     &         psp(its:ite)
      logical  ldflag(its:ite)

      integer  j
      integer   kcall,kk
      real     zqmax,zqsat,zcor,zqp,zcond,zcond1,zl,zi,zf,rv,rd,alv,als,rcpd,vtmpc1
      real     tmelt, c2es, c3les, c3ies, c4les, c4ies, c5les, c5ies, r5alvcp, r5alscp



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


   REAL FUNCTION fpvs(t,ice,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c)

   IMPLICIT NONE

   REAL :: t,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c,dldt,xa,xb,dldti,         &
           xai,xbi,ttp,tr
   INTEGER :: ice

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

   if (t.lt.180.) then
     tr=ttp/180.
     if(t.lt.ttp.and.ice.eq.1) then
       fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
     else
       fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
     endif
   endif

   if (t.ge.330.) then
     tr=ttp/330
     if(t.lt.ttp.and.ice.eq.1) then
       fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
     else
       fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
     endif
   endif

   END FUNCTION fpvs



   subroutine nsas2init(rthcuten,rqvcuten,rqccuten,rqicuten,                    &
                      rucuten,rvcuten,                                         &  
                      restart,p_qc,p_qi,p_first_scalar,                        &
                      allowed_to_read,                                         &
                      ids, ide, jds, jde, kds, kde,                            &
                      ims, ime, jms, jme, kms, kme,                            &
                      its, ite, jts, jte, kts, kte                  )

   implicit none

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

   jtf=min0(jte,jde-1)
   ktf=min0(kte,kde-1)
   itf=min0(ite,ide-1)

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

     if (p_qc .ge. p_first_scalar) then
       do j = jts,jtf
         do k = kts,ktf
           do i = its,itf
             rqccuten(i,k,j)=0.
           enddo
         enddo
       enddo
     endif

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

   end subroutine nsas2init



  
      real function foealfa(tt)
  
  
  
  
  
  
  
  
        implicit none
        real tt
        real rtwat, rtice

        rtwat=273.16
        rtice=273.16-23.
         foealfa = min(1.,((max(rtice,min(rtwat,tt))-rtice) &
     &  /(rtwat-rtice))**2)
  
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

END MODULE module_cu_ksas2



